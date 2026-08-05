package com.enthalpy.notiforward;

import android.app.Activity;
import android.app.NotificationManager;
import android.content.ComponentName;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.Settings;
import android.text.method.ScrollingMovementMethod;
import android.widget.Button;
import android.widget.EditText;
import android.widget.Switch;
import android.widget.TextView;

import java.text.SimpleDateFormat;
import java.util.Date;
import java.util.Locale;

public class MainActivity extends Activity {

    private EditText editTopic;
    private EditText editPackageFilter;
    private Switch switchWeChatOnly;
    private Button btnToggleAccess;
    private Button btnBatteryOptimize;
    private Button btnTest;
    private Button btnBlockList;
    private TextView txtStatus;
    private TextView txtQueue;
    private TextView txtLog;
    private SharedPreferences prefs;
    private QueueManager queueManager;
    private final Handler handler = new Handler(Looper.getMainLooper());

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        prefs = getSharedPreferences("notiforward", MODE_PRIVATE);
        queueManager = new QueueManager(this);

        editTopic = findViewById(R.id.editTopic);
        editPackageFilter = findViewById(R.id.editPackageFilter);
        switchWeChatOnly = findViewById(R.id.switchWeChatOnly);
        btnToggleAccess = findViewById(R.id.btnToggleAccess);
        btnBatteryOptimize = findViewById(R.id.btnBatteryOptimize);
        btnTest = findViewById(R.id.btnTest);
        btnBlockList = findViewById(R.id.btnBlockList);
        txtStatus = findViewById(R.id.txtStatus);
        txtQueue = findViewById(R.id.txtQueue);
        txtLog = findViewById(R.id.txtLog);
        txtLog.setMovementMethod(new ScrollingMovementMethod());

        String savedTopic = prefs.getString("topic", "");
        if (savedTopic.isEmpty()) {
            savedTopic = "notiforward-" + System.currentTimeMillis();
            prefs.edit().putString("topic", savedTopic).apply();
        }
        editTopic.setText(savedTopic);
        String savedFilter = prefs.getString("package_filter", "");
        editPackageFilter.setText(savedFilter);
        // 恢复仅微信开关状态（默认 true = 仅微信，与旧版行为一致）
        switchWeChatOnly.setChecked(prefs.getBoolean("wechat_only", true));

        // Android 13+ 通知运行时权限：不授权则前台保活通知不显示，用户无法感知服务状态
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            NotificationManager nm = (NotificationManager) getSystemService(NOTIFICATION_SERVICE);
            if (!nm.areNotificationsEnabled()) {
                requestPermissions(new String[]{android.Manifest.permission.POST_NOTIFICATIONS}, 100);
            }
        }

        btnToggleAccess.setOnClickListener(v -> {
            if (isNotificationListenerEnabled()) {
                txtStatus.setText("通知权限已开启");
            } else {
                startActivity(new android.content.Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS));
            }
        });

        // 电池优化白名单引导（防被杀后台）
        btnBatteryOptimize.setOnClickListener(v -> {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                Intent intent = new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS);
                intent.setData(Uri.parse("package:" + getPackageName()));
                try {
                    startActivity(intent);
                } catch (Exception e) {
                    // 部分 ROM 不支持直接跳转，退回设置页
                    startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
                }
            } else {
                appendLog("当前系统版本无需设置电池优化");
            }
        });

        btnTest.setOnClickListener(v -> {
            saveSettings();
            String topic = editTopic.getText().toString().trim();
            String msg = "测试消息 from NotiForward at " + new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
            new Thread(() -> {
                boolean ok = NotificationForwardService.sendToNtfy(topic, msg);
                runOnUiThread(() -> appendLog(ok ? "测试发送成功" : "测试发送失败"));
            }).start();
        });

        // 屏蔽群管理入口
        btnBlockList.setOnClickListener(v -> startActivity(new Intent(this, BlockListActivity.class)));

        updateStatus();
        handler.postDelayed(this::updateStatus, 1000);
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        // 移除延迟回调，避免销毁后仍触碰已 detach 的 View
        handler.removeCallbacksAndMessages(null);
    }

    private void saveSettings() {
        prefs.edit()
                .putString("topic", editTopic.getText().toString().trim())
                .putString("package_filter", editPackageFilter.getText().toString().trim())
                .putBoolean("wechat_only", switchWeChatOnly.isChecked())
                .apply();
    }

    @Override
    protected void onPause() {
        super.onPause();
        saveSettings();
    }

    private boolean isNotificationListenerEnabled() {
        String flat = Settings.Secure.getString(getContentResolver(), "enabled_notification_listeners");
        return flat != null && flat.contains(getPackageName());
    }

    private void updateStatus() {
        boolean enabled = isNotificationListenerEnabled();
        txtStatus.setText(enabled ? "状态: 运行中" : "状态: 未开启通知权限");
        btnToggleAccess.setText(enabled ? "已开启 (点击检查)" : "开启通知权限");
        // 队列待补发状态
        int q = queueManager.size();
        txtQueue.setText(q > 0 ? "待补发: " + q + " 条（网络恢复后自动补发）" : "待补发: 0 条");
    }

    public void appendLog(String msg) {
        String ts = new SimpleDateFormat("HH:mm:ss", Locale.getDefault()).format(new Date());
        String line = "[" + ts + "] " + msg + "\n";
        txtLog.append(line);
    }
}
