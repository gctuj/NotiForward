package com.enthalpy.notiforward;

import android.content.Context;
import android.content.SharedPreferences;

import org.json.JSONArray;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;

/**
 * 屏蔽名单管理（黑名单模式）
 * - 屏蔽关键词存 SharedPreferences（JSON 数组），支持包含匹配
 * - 首次使用预填游戏群：fpsのgun king、永劫糕手
 * - 同时记录"最近收到的群/联系人名"（seen_titles），供屏蔽管理界面勾选
 */
public class BlockListManager {

    private static final String PREFS = "notiforward";
    private static final String KEY_BLOCK = "block_keywords";
    private static final String KEY_SEEN = "seen_titles";
    private static final int MAX_SEEN = 50;

    /** 预填的屏蔽名单（游戏群，2026-08-05 用户确认） */
    private static final String[] DEFAULT_BLOCK = {
            "fpsのgun king",
            "永劫糕手"
    };

    private final SharedPreferences prefs;

    public BlockListManager(Context context) {
        prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE);
        // 首次使用（无 key 记录）时预填默认屏蔽名单
        if (!prefs.contains(KEY_BLOCK)) {
            saveKeywords(new ArrayList<>(Arrays.asList(DEFAULT_BLOCK)));
        }
    }

    /** 获取屏蔽关键词列表 */
    public synchronized List<String> getKeywords() {
        String json = prefs.getString(KEY_BLOCK, "[]");
        List<String> list = new ArrayList<>();
        try {
            JSONArray arr = new JSONArray(json);
            for (int i = 0; i < arr.length(); i++) list.add(arr.getString(i));
        } catch (Exception ignored) {
        }
        return list;
    }

    /** 保存屏蔽关键词列表 */
    public synchronized void saveKeywords(List<String> keywords) {
        JSONArray arr = new JSONArray();
        for (String s : keywords) {
            if (!s.trim().isEmpty()) arr.put(s.trim());
        }
        prefs.edit().putString(KEY_BLOCK, arr.toString()).apply();
    }

    /** 添加屏蔽关键词（自动去重） */
    public synchronized void addKeyword(String keyword) {
        String kw = keyword == null ? "" : keyword.trim();
        if (kw.isEmpty()) return;
        List<String> list = getKeywords();
        for (String s : list) {
            if (s.equals(kw)) return;
        }
        list.add(kw);
        saveKeywords(list);
    }

    /** 删除屏蔽关键词 */
    public synchronized void removeKeyword(String keyword) {
        List<String> list = getKeywords();
        list.remove(keyword);
        saveKeywords(list);
    }

    /** 判断标题（群名/联系人名）是否命中屏蔽关键词（包含匹配） */
    public synchronized boolean isBlocked(String title) {
        if (title == null || title.isEmpty()) return false;
        for (String kw : getKeywords()) {
            if (title.contains(kw)) return true;
        }
        return false;
    }

    /** 记录一个收到的群/联系人名（去重，新的在前，上限 50） */
    public synchronized void recordSeenTitle(String title) {
        if (title == null || title.trim().isEmpty()) return;
        String t = title.trim();
        List<String> seen = getSeenTitles();
        seen.remove(t);
        seen.add(0, t);
        if (seen.size() > MAX_SEEN) {
            seen = new ArrayList<>(seen.subList(0, MAX_SEEN));
        }
        JSONArray arr = new JSONArray();
        for (String s : seen) arr.put(s);
        prefs.edit().putString(KEY_SEEN, arr.toString()).apply();
    }

    /** 获取最近收到的群/联系人名 */
    public synchronized List<String> getSeenTitles() {
        String json = prefs.getString(KEY_SEEN, "[]");
        List<String> list = new ArrayList<>();
        try {
            JSONArray arr = new JSONArray(json);
            for (int i = 0; i < arr.length(); i++) list.add(arr.getString(i));
        } catch (Exception ignored) {
        }
        return list;
    }
}
