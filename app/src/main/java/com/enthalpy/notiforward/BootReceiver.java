package com.enthalpy.notiforward;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

/**
 * 开机自启：系统启动完成后，提示用户开启通知监听（或恢复前台服务保活）。
 * 注：NotificationListenerService 无法直接 startService 拉起，
 * 这里通过尝试访问监听服务状态 + 拉起 Activity 引导用户，或者直接尝试 startForegroundService。
 */
public class BootReceiver extends BroadcastReceiver {

    private static final String TAG = "NotiForward";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (!Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            return;
        }
        Log.i(TAG, "Boot completed, trying to start service");
        try {
            Intent service = new Intent(context, NotificationForwardService.class);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                context.startForegroundService(service);
            } else {
                context.startService(service);
            }
        } catch (Exception e) {
            Log.e(TAG, "startForegroundService failed, need user open access first", e);
            // 通知监听服务未授权时无法启动，拉起主界面引导用户
            try {
                Intent main = new Intent(context, MainActivity.class);
                main.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                context.startActivity(main);
            } catch (Exception e2) {
                Log.e(TAG, "open MainActivity failed", e2);
            }
        }
    }
}
