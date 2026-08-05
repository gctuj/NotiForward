package com.enthalpy.notiforward;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

/**
 * 发送队列管理（失败重试，借鉴 Wimboro/NotificationListener 的 pending 设计，轻量实现）
 * - 队列存 SharedPreferences（JSON 数组），每条含 topic/payload/retry/time
 * - 上限 200 条（满了丢最旧）；单条重试 50 次后丢弃
 * - 线程安全：所有公开方法 synchronized
 */
public class QueueManager {

    private static final String PREFS = "notiforward";
    private static final String KEY_QUEUE = "pending_queue";
    private static final int MAX_QUEUE = 200;
    private static final int MAX_RETRY = 50;

    private final SharedPreferences prefs;

    public QueueManager(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
    }

    /** 当前待补发条数 */
    public synchronized int size() {
        return getQueue().length();
    }

    /** 消息入队（转发失败时调用） */
    public synchronized void enqueue(String topic, String payload) {
        JSONArray queue = getQueue();
        JSONObject item = new JSONObject();
        try {
            item.put("topic", topic);
            item.put("payload", payload);
            item.put("retry", 0);
            item.put("time", System.currentTimeMillis());
        } catch (Exception ignored) {
        }
        queue.put(item);
        // 上限 200：超了丢最旧的
        while (queue.length() > MAX_QUEUE) {
            queue.remove(0);
        }
        prefs.edit().putString(KEY_QUEUE, queue.toString()).apply();
    }

    /** 尝试补发队列中所有消息；成功移除，失败 retry+1，只有超过重试上限才丢弃。返回成功发送条数 */
    public synchronized int flush() {
        JSONArray queue = getQueue();
        JSONArray remaining = new JSONArray();
        int sent = 0;
        for (int i = 0; i < queue.length(); i++) {
            try {
                JSONObject item = queue.getJSONObject(i);
                String topic = item.getString("topic");
                String payload = item.getString("payload");
                boolean ok;
                try {
                    ok = NotificationForwardService.sendToNtfy(topic, payload);
                } catch (Exception e) {
                    ok = false; // 发送异常同样视为失败，保留重试
                }
                if (ok) {
                    sent++;
                    continue;
                }
                int retry = item.optInt("retry", 0) + 1;
                if (retry >= MAX_RETRY) continue; // 只有超过重试上限才丢弃
                item.put("retry", retry);
                remaining.put(item);
            } catch (Exception ignored) {
                // 单条数据损坏：保留并降级为重试计数，避免静默丢失
                try {
                    JSONObject item = queue.getJSONObject(i);
                    int retry = item.optInt("retry", 0) + 1;
                    if (retry < MAX_RETRY) {
                        item.put("retry", retry);
                        remaining.put(item);
                    }
                } catch (Exception e2) {
                    // 条目完全损坏且无法修复，只能放弃（记录日志由上层观察）
                    android.util.Log.e("NotiForward", "queue item corrupted, dropped", e2);
                }
            }
        }
        prefs.edit().putString(KEY_QUEUE, remaining.toString()).apply();
        return sent;
    }

    private JSONArray getQueue() {
        String json = prefs.getString(KEY_QUEUE, "[]");
        try {
            return new JSONArray(json);
        } catch (Exception e) {
            return new JSONArray();
        }
    }
}
