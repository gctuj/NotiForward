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

    /** 队列项唯一 id 生成器：enqueue 与 flush 合并时用 id 判断"是否快照后新入队"，
     *  避免用时间戳比较在极端（同毫秒入队）情况下丢失新条目 */
    private static final java.util.concurrent.atomic.AtomicLong SEQ =
            new java.util.concurrent.atomic.AtomicLong(System.nanoTime());

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
            item.put("id", SEQ.incrementAndGet());
            item.put("topic", topic);
            item.put("payload", payload);
            item.put("retry", 0);
            item.put("time", System.currentTimeMillis());
            item.put("next_retry_at", System.currentTimeMillis()); // 立即可发（首次尝试）
        } catch (Exception ignored) {
        }
        queue.put(item);
        // 上限 200：超了丢最旧的
        while (queue.length() > MAX_QUEUE) {
            queue.remove(0);
        }
        prefs.edit().putString(KEY_QUEUE, queue.toString()).commit();
    }

    /** 指数退避间隔：60s * 2^min(retry,5)，封顶 32 分钟（吸收 ItsAzni 的 DB 层退避思路）。
     *  比固定 60s 全量重试省电：断网时重试间隔逐次拉长，不空耗电。 */
    private static long backoffMillis(int retry) {
        return 60_000L << Math.min(retry, 5);
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
        // 记录快照的最大入队时间与全部 id，用于合并快照期间并发新入队的条目
        long snapshotMaxTime = 0;
        java.util.Set<Long> snapshotIds = new java.util.HashSet<>();
        for (int i = 0; i < snapshot.length(); i++) {
            JSONObject it = snapshot.optJSONObject(i);
            if (it != null) {
                snapshotMaxTime = Math.max(snapshotMaxTime, it.optLong("time", 0));
                snapshotIds.add(it.optLong("id", 0));
            }
        }

        // ===== 锁外发送（网络 I/O 不占锁，主线程不再被拖住） =====
        JSONArray remaining = new JSONArray();
        int sent = 0;
        long now = System.currentTimeMillis();
        for (int i = 0; i < snapshot.length(); i++) {
            JSONObject item = snapshot.optJSONObject(i);
            if (item == null) continue;
            // 未到退避时间的条目原样保留，不重试不计数（省电，断网时不空耗）
            if (now < item.optLong("next_retry_at", 0)) {
                remaining.put(item);
                continue;
            }
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
                item.put("next_retry_at", now + backoffMillis(retry)); // 指数退避，下次到期才再试
                remaining.put(item);
            } catch (Exception ignored) {
                // 单条数据损坏：保留并降级为重试计数，避免静默丢失
                try {
                    int retry = item.optInt("retry", 0) + 1;
                    if (retry < MAX_RETRY) {
                        item.put("retry", retry);
                        item.put("next_retry_at", now + backoffMillis(retry));
                        remaining.put(item);
                    }
                } catch (Exception e2) {
                    // 条目完全损坏且无法修复，只能放弃（记录日志由上层观察）
                    Log.e("NotiForward", "queue item corrupted, dropped", e2);
                }
            }
        }

        synchronized (this) {
            // 合并快照期间并发新入队的条目（用唯一 id 判断，避免时间戳同毫秒竞态丢消息）
            JSONArray current = getQueue();
            for (int i = 0; i < current.length(); i++) {
                JSONObject it = current.optJSONObject(i);
                if (it != null
                        && it.optLong("time", 0) >= snapshotMaxTime
                        && !snapshotIds.contains(it.optLong("id", 0))) {
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
