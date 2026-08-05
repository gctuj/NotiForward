package com.enthalpy.notiforward;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.provider.Settings;
import android.util.Log;

/**
 * 开机自启（引导式）。
 * 注意：NotificationListenerService 有 BIND_NOTIFICATION_LISTENER_SERVICE 权限限制，
 * 普通进程 startForegroundService 必然失败（旧实现每次都抛异常后拉 Activity，
 * 而 Android 10+ 禁止后台启动 Activity，等于开机后完全无效）。
 * 系统会在开机后按 enabled_notification_listeners 自动重绑 NLS —— 本 Receiver 只做两件事：
 * 1. 若监听已启用，尝试恢复前台服务保活（失败无害）；
 * 2. 若监听未启用（ROM 重置了权限），发一条通知引导用户重新开启，不强行弹 Activity。
 */
public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "NotiForward";
    private static final String CHANNEL_ID = "notiforward_keepalive";
    private static final int NOTIFY_ID = 2001;

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        Log.i(TAG, "Boot completed");
        if (!isListenerEnabled(context)) {
            Log.w(TAG, "通知监听未启用（可能被 ROM 重置），发送引导通知");
            notifyGuideUser(context);
            return;
        }
        // 监听已启用：尝试恢复前台服务（系统随后也会按监听设置自动重绑 NLS，此处失败无害）
        try {
            Intent service = new Intent(context, NotificationForwardService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(service);
            } else {
                context.startService(service);
            }
            Log.i(TAG, "foreground service start attempted");
        } catch (Exception e) {
            // 后台启动限制/未授权等：忽略，系统会自动重绑 NLS
            Log.e(TAG, "start service failed (non-fatal, system will rebind NLS)", e);
        }
    }

    private boolean isListenerEnabled(Context context) {
        String flat = Settings.Secure.getString(context.getContentResolver(),
                "enabled_notification_listeners");
        return flat != null && flat.contains(context.getPackageName());
    }

    /** 发一条引导通知（不开 Activity，避免 Android 10+ 后台启动限制） */
    private void notifyGuideUser(Context context) {
        try {
            NotificationManager nm = (NotificationManager) context.getSystemService(Context.NOTIFICATION_SERVICE);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                NotificationChannel channel = new NotificationChannel(
                        CHANNEL_ID, "NotiForward 保活", NotificationManager.IMPORTANCE_HIGH);
                channel.setShowBadge(false);
                nm.createNotificationChannel(channel);
            }
            Intent open = new Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS);
            open.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            PendingIntent pi = PendingIntent.getActivity(
                    context, 0, open,
                    Build.VERSION.SDK_INT >= Build.VERSION_CODES.M
                            ? PendingIntent.FLAG_IMMUTABLE : 0);
            Notification.Builder builder;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                builder = new Notification.Builder(context, CHANNEL_ID);
            } else {
                builder = new Notification.Builder(context);
            }
            Notification n = builder
                    .setContentTitle("NotiForward 需要重新开启")
                    .setContentText("开机后发现通知监听未启用，点此重新开启（部分手机系统会重置此权限）")
                    .setSmallIcon(android.R.drawable.ic_popup_sync)
                    .setContentIntent(pi)
                    .setAutoCancel(true)
                    .build();
            nm.notify(NOTIFY_ID, n);
        } catch (Exception e) {
            Log.e(TAG, "guide notification failed", e);
        }
    }
}
