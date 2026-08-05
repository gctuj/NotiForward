package com.enthalpy.notiforward;

import android.app.Activity;
import android.os.Bundle;
import android.view.View;
import android.widget.AdapterView;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.ListView;
import android.widget.Toast;

import java.util.ArrayList;
import java.util.List;

/**
 * 屏蔽群管理界面
 * - 上区：手动输入关键词 + 添加
 * - 中区：当前屏蔽列表（点击删除）
 * - 下区：最近收到的群/联系人（自动收集，点击加入屏蔽）
 */
public class BlockListActivity extends Activity {

    private BlockListManager blockList;
    private EditText editKeyword;
    private ListView listBlocked;
    private ListView listSeen;
    private ArrayAdapter<String> blockedAdapter;
    private ArrayAdapter<String> seenAdapter;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_block_list);

        blockList = new BlockListManager(this);
        editKeyword = findViewById(R.id.editKeyword);
        listBlocked = findViewById(R.id.listBlocked);
        listSeen = findViewById(R.id.listSeen);

        blockedAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, new ArrayList<>());
        seenAdapter = new ArrayAdapter<>(this, android.R.layout.simple_list_item_1, new ArrayList<>());
        listBlocked.setAdapter(blockedAdapter);
        listSeen.setAdapter(seenAdapter);

        Button btnAdd = findViewById(R.id.btnAddKeyword);
        btnAdd.setOnClickListener(v -> {
            String kw = editKeyword.getText().toString().trim();
            if (kw.isEmpty()) {
                Toast.makeText(this, "请输入关键词", Toast.LENGTH_SHORT).show();
                return;
            }
            blockList.addKeyword(kw);
            editKeyword.setText("");
            refresh();
            Toast.makeText(this, "已添加屏蔽: " + kw, Toast.LENGTH_SHORT).show();
        });

        // 点击屏蔽列表条目 = 删除该屏蔽
        listBlocked.setOnItemClickListener((parent, view, position, id) -> {
            String kw = blockedAdapter.getItem(position);
            blockList.removeKeyword(kw);
            refresh();
            Toast.makeText(this, "已取消屏蔽: " + kw, Toast.LENGTH_SHORT).show();
        });

        // 点击"最近收到"条目 = 加入屏蔽
        listSeen.setOnItemClickListener((parent, view, position, id) -> {
            String title = seenAdapter.getItem(position);
            if (blockList.isBlocked(title)) {
                Toast.makeText(this, "已在屏蔽列表中", Toast.LENGTH_SHORT).show();
                return;
            }
            blockList.addKeyword(title);
            refresh();
            Toast.makeText(this, "已屏蔽: " + title, Toast.LENGTH_SHORT).show();
        });

        refresh();
    }

    private void refresh() {
        blockedAdapter.clear();
        blockedAdapter.addAll(blockList.getKeywords());
        blockedAdapter.notifyDataSetChanged();

        // "最近收到"列表排除已在屏蔽中的
        List<String> seen = new ArrayList<>();
        for (String t : blockList.getSeenTitles()) {
            if (!blockList.isBlocked(t)) seen.add(t);
        }
        seenAdapter.clear();
        seenAdapter.addAll(seen);
        seenAdapter.notifyDataSetChanged();
    }
}
