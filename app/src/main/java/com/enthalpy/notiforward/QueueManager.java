package com.enthalpy.notiforward;

import android.content.Context;
import android.content.SharedPreferences;
import android.util.Log;

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

    /** 当前待补发条数。只读且 SharedPreferences 读取线程安全，不加锁：
     *  避免与 flush 的网络 I/O（最长 2000s）互相阻塞导致主线程 ANR */
    public int size() {
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
        prefs.edit().putString(KEY_QUEUE, queue.toString()).commit();
    }

    /** 尝试补发队列中所有消息；成功移除，失败 retry+1，只有超过重试上限才丢弃。返回成功发送条数。
     *  修复（P0）：原实现整个方法 synchronized，持锁逐条做最长 10s 的网络 I/O（200 条最坏 2000s），
     *  主线程调用 size()/enqueue() 会被无界阻塞 → ANR。现改为：
     *  锁内取快照 → 锁外逐条发送 → 锁内合并并发新入队条目后写回。 */
    public int flush() {
        JSONArray snapshot;
        synchronized (this) {
            snapshot = getQueue();
        }
        // 记录快照的最大入队时间，用于合并快照期间新入队的条目
        long snapshotMaxTime = 0;
        for (int i = 0; i < snapshot.length(); i++) {
            JSONObject it = snapshot.optJSONObject(i);
            if (it != null) {
                snapshotMaxTime = Math.max(snapshotMaxTime, it.optLong("time", 0));
            }
        }

        // ===== 锁外发送（网络 I/O 不占锁，主线程不再被拖住） =====
        JSONArray remaining = new JSONArray();
        int sent = 0;
        for (int i = 0; i < snapshot.length(); i++) {
            JSONObject item = snapshot.optJSONObject(i);
            if (item == null) continue;
            try {
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
                if (retry >= MAX_RETRY) {
                    Log.w("NotiForward", "queue item dropped after " + MAX_RETRY + " retries: " + topic);
                    continue;
                }
                item.put("retry", retry);
                remaining.put(item);
            } catch (Exception ignored) {
                // 单条数据损坏：保留并降级为重试计数，避免静默丢失
                try {
                    int retry = item.optInt("retry", 0) + 1;
                    if (retry < MAX_RETRY) {
                        item.put("retry", retry);
                        remaining.put(item);
                    }
                } catch (Exception e2) {
                    // 条目完全损坏且无法修复，只能放弃（记录日志由上层观察）
                    Log.e("NotiForward", "queue item corrupted, dropped", e2);
                }
            }
        }

        synchronized (this) {
            // 合并快照期间新入队的条目（入队时间大于快照最大时间），避免被覆盖丢失
            JSONArray current = getQueue();
            for (int i = 0; i < current.length(); i++) {
                JSONObject it = current.optJSONObject(i);
                if (it != null && it.optLong("time", 0) > snapshotMaxTime) {
                    remaining.put(it);
                }
            }
            prefs.edit().putString(KEY_QUEUE, remaining.toString()).commit();
        }
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
