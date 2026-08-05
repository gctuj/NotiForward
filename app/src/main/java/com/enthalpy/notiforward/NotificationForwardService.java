package com.enthalpy.notiforward;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.Context;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.service.notification.NotificationListenerService;
import android.service.notification.StatusBarNotification;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.Date;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public class NotificationForwardService extends NotificationListenerService {

    private static final String TAG = "NotiForward";
    private static final String NTFY_BASE = "https://ntfy.sh";
    private static final String CHANNEL_ID = "notiforward_keepalive";
    private static final int FOREGROUND_ID = 1001;
    // 队列补发周期：60 秒
    private static final long QUEUE_FLUSH_INTERVAL = 60_000L;
    // 默认放行的应用包名：微信 + QQ（留空过滤时使用）
    private static final String[] DEFAULT_PACKAGES = {
            "com.tencent.mm",          // 微信
            "com.tencent.mobileqq"     // QQ
    };

    private SharedPreferences prefs;
    private BlockListManager blockList;
    private QueueManager queueManager;
    private final ExecutorService executor = Executors.newSingleThreadExecutor();
    private final Set<String> recentKeys = new HashSet<>();
    private PowerManager.WakeLock wakeLock;
    private final Handler handler = new Handler(Looper.getMainLooper());

    /** 定时补发队列中的失败消息 */
    private final Runnable queueFlusher = new Runnable() {
        @Override
        public void run() {
            try {
                int sent = queueManager.flush();
                if (sent > 0) {
                    Log.i(TAG, "队列补发成功 " + sent + " 条，剩余 " + queueManager.size() + " 条");
                }
            } catch (Exception e) {
                Log.e(TAG, "queue flush error", e);
            }
            handler.postDelayed(this, QUEUE_FLUSH_INTERVAL);
        }
    };

    @Override
    public void onCreate() {
        super.onCreate();
        prefs = getSharedPreferences("notiforward", MODE_PRIVATE);
        blockList = new BlockListManager(this);
        queueManager = new QueueManager(this);
        startForeground(FOREGROUND_ID, buildKeepAliveNotification());
        acquireWakeLock();
        handler.postDelayed(queueFlusher, QUEUE_FLUSH_INTERVAL);
    }

    @Override
    public void onDestroy() {
        super.onDestroy();
        handler.removeCallbacks(queueFlusher);
        if (wakeLock != null && wakeLock.isHeld()) {
            wakeLock.release();
            Log.i(TAG, "WakeLock released");
        }
    }

    /** 创建常驻通知（前台服务保活，防止被系统杀掉） */
    private Notification buildKeepAliveNotification() {
        NotificationManager nm = (NotificationManager) getSystemService(Context.NOTIFICATION_SERVICE);
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                    CHANNEL_ID, "NotiForward 保活", NotificationManager.IMPORTANCE_MIN);
            channel.setShowBadge(false);
            nm.createNotificationChannel(channel);
        }
        Intent intent = new Intent(this, MainActivity.class);
        PendingIntent pi = PendingIntent.getActivity(
                this, 0, intent,
                Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                        ? PendingIntent.FLAG_IMMUTABLE : 0);
        Notification.Builder builder;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            builder = new Notification.Builder(this, CHANNEL_ID);
        } else {
            builder = new Notification.Builder(this);
        }
        return builder
                .setContentTitle("NotiForward 运行中")
                .setContentText("正在监听微信通知，勿关闭此通知")
                .setSmallIcon(android.R.drawable.ic_popup_sync)
                .setContentIntent(pi)
                .setOngoing(true)
                .setPriority(Notification.PRIORITY_MIN)
                .build();
    }

    /** 获取 WakeLock，防止 CPU 休眠导致监听中断 */
    private void acquireWakeLock() {
        try {
            PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
            wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "NotiForward:keepalive");
            wakeLock.acquire();
            Log.i(TAG, "WakeLock acquired");
        } catch (Exception e) {
            Log.e(TAG, "WakeLock error", e);
        }
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        // START_STICKY：服务被系统杀掉后尝试自动重启
        return START_STICKY;
    }

    @Override
    public void onNotificationPosted(StatusBarNotification sbn) {
        try {
            handleNotification(sbn);
        } catch (Exception e) {
            Log.e(TAG, "onNotificationPosted error", e);
        }
    }

    @Override
    public void onNotificationRemoved(StatusBarNotification sbn) {
    }

    private void handleNotification(StatusBarNotification sbn) {
        String packageName = sbn.getPackageName();
        String filter = prefs.getString("package_filter", "");
        boolean wechatOnly = prefs.getBoolean("wechat_only", false);

        // 包名过滤：filter 非空时按逗号分隔的多包名匹配；
        // 为空时用默认列表（微信+QQ），仅微信开关开启时只放行微信
        String[] allowed;
        if (!filter.trim().isEmpty()) {
            allowed = filter.split("\\s*,\\s*");
        } else if (wechatOnly) {
            allowed = new String[]{"com.tencent.mm"};
        } else {
            allowed = DEFAULT_PACKAGES;
        }
        boolean matched = false;
        for (String pkg : allowed) {
            if (pkg.isEmpty()) continue;
            if (packageName.equals(pkg.trim()) || packageName.startsWith(pkg.trim() + ".")) {
                matched = true;
                break;
            }
        }
        if (!matched) return;

        Notification notification = sbn.getNotification();
        if (notification == null) return;

        Bundle extras = notification.extras;
        if (extras == null) return;

        // ===== 全面提取通知字段 =====
        String title = safeStr(extras.getCharSequence(Notification.EXTRA_TITLE));
        String text = safeStr(extras.getCharSequence(Notification.EXTRA_TEXT));
        String bigText = safeStr(extras.getCharSequence(Notification.EXTRA_BIG_TEXT));
        String subText = safeStr(extras.getCharSequence(Notification.EXTRA_SUB_TEXT));
        String summaryText = safeStr(extras.getCharSequence(Notification.EXTRA_SUMMARY_TEXT));
        String infoText = safeStr(extras.getCharSequence(Notification.EXTRA_INFO_TEXT));
        String bigTitle = safeStr(extras.getCharSequence(Notification.EXTRA_TITLE_BIG));

        // InboxStyle: 多条消息（微信多条消息时用这个）
        CharSequence[] textLines = extras.getCharSequenceArray(Notification.EXTRA_TEXT_LINES);
        List<String> inboxLines = new ArrayList<>();
        if (textLines != null) {
            for (CharSequence line : textLines) {
                if (line != null && line.length() > 0) {
                    inboxLines.add(line.toString());
                }
            }
        }

        // 进度条信息
        int progress = extras.getInt(Notification.EXTRA_PROGRESS, -1);
        int progressMax = extras.getInt(Notification.EXTRA_PROGRESS_MAX, -1);

        // 优先用 bigText（展开后的完整内容），没有就退回 text
        String fullText = !bigText.isEmpty() ? bigText : text;

        if (title.isEmpty() && fullText.isEmpty() && inboxLines.isEmpty()) return;

        // ===== 屏蔽名单过滤（黑名单模式，按群名/联系人名包含匹配）=====
        // 记录收到的群/联系人名，供屏蔽管理界面使用
        blockList.recordSeenTitle(title);
        if (blockList.isBlocked(title)) {
            Log.i(TAG, "已屏蔽(黑名单): " + title);
            return;
        }

        // 去重
        String dedupKey = packageName + "|" + title + "|" + fullText + "|" + inboxLines.toString();
        synchronized (recentKeys) {
            if (recentKeys.contains(dedupKey)) return;
            recentKeys.add(dedupKey);
            if (recentKeys.size() > 200) {
                recentKeys.clear();
                recentKeys.add(dedupKey);
            }
        }

        // 获取应用名
        String appName;
        try {
            appName = getPackageManager().getApplicationLabel(
                    getPackageManager().getApplicationInfo(packageName, 0)).toString();
        } catch (PackageManager.NameNotFoundException e) {
            appName = packageName;
        }

        String timeStr = new SimpleDateFormat("yyyy-MM-dd HH:mm:ss", Locale.getDefault())
                .format(new Date(sbn.getPostTime()));

        // 构建 JSON（包含所有能拿到的字段）
        JSONObject json = new JSONObject();
        try {
            json.put("app", appName);
            json.put("package", packageName);
            json.put("time", timeStr);
            json.put("title", title);
            json.put("text", text);
            json.put("full_text", fullText);

            if (!subText.isEmpty()) json.put("sub_text", subText);
            if (!summaryText.isEmpty()) json.put("summary_text", summaryText);
            if (!infoText.isEmpty()) json.put("info_text", infoText);
            if (!bigTitle.isEmpty()) json.put("big_title", bigTitle);

            if (!inboxLines.isEmpty()) {
                JSONArray arr = new JSONArray();
                for (String line : inboxLines) arr.put(line);
                json.put("text_lines", arr);
                json.put("line_count", inboxLines.size());
            }

            if (progress >= 0) {
                json.put("progress", progress);
                json.put("progress_max", progressMax);
            }

            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                json.put("channel_id", notification.getChannelId());
            }

            json.put("priority", notification.priority);
            json.put("is_group", sbn.isGroup());

            int actionCount = notification.actions != null ? notification.actions.length : 0;
            json.put("action_count", actionCount);

        } catch (Exception e) {
            Log.e(TAG, "JSON build error", e);
            return;
        }

        final String payload = json.toString();
        String topic = prefs.getString("topic", "");
        if (topic.isEmpty()) return;

        Log.i(TAG, "Forwarding: " + title + " | " + fullText
                + " | lines=" + inboxLines.size());

        executor.execute(() -> sendWithQueue(topic, payload));
    }

    /** 发送消息：失败进队列，由定时任务补发（防漏） */
    private void sendWithQueue(String topic, String payload) {
        boolean ok = sendToNtfy(topic, payload);
        if (!ok) {
            queueManager.enqueue(topic, payload);
            Log.i(TAG, "发送失败，已入队待补发，队列剩余 " + queueManager.size() + " 条");
        }
    }

    private static String safeStr(CharSequence cs) {
        return cs != null ? cs.toString() : "";
    }

    public static boolean sendToNtfy(String topic, String message) {
        try {
            URL url = new URL(NTFY_BASE + "/" + topic);
            HttpURLConnection conn = (HttpURLConnection) url.openConnection();
            conn.setRequestMethod("POST");
            conn.setRequestProperty("Content-Type", "application/json");
            conn.setDoOutput(true);
            conn.setConnectTimeout(10000);
            conn.setReadTimeout(10000);
            OutputStream os = conn.getOutputStream();
            os.write(message.getBytes(StandardCharsets.UTF_8));
            os.flush();
            os.close();
            int code = conn.getResponseCode();
            conn.disconnect();
            Log.i(TAG, "ntfy response: " + code);
            return code >= 200 && code < 300;
        } catch (Exception e) {
            Log.e(TAG, "sendToNtfy error", e);
            return false;
        }
    }
}
