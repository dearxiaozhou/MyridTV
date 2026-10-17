/* 资产目录设置页：读/改资产主路径 + 旧目录搬迁。
   后端端口可能漂移，所以基址一律先读 /static/app_config.json 里的 proxy.base_url。 */
(function () {
    'use strict';

    var DEFAULT_BASE = 'http://127.0.0.1:3107';
    var state = { base: '', data: null, migrating: false, timer: null };

    // 校验规则：默认隐藏，仅在保存出错/校验不过时显示（按方案收敛提示噪音）
    var RULE_HINT = '填绝对路径；目录不存在会自动创建（含 output/input/library/blender 等子目录）。不能选软件安装目录本身、数据目录、盘符根目录或系统目录。';

    var el = {};
    ['arCurrentDir', 'arSourceTag', 'arMeta', 'arInput', 'arSaveBtn', 'arDefaultBtn',
     'arSaveStatus', 'arLegacyDir', 'arMigrateBtn', 'arMigrateProgress', 'arMigrateBar',
     'arPendingPill', 'arMigrateSection', 'arHint', 'arBrowseBtn', 'arMigrateNote'
    ].forEach(function (id) { el[id] = document.getElementById(id); });

    function showHint(text) {
        if (!el.arHint) return;
        el.arHint.textContent = text || RULE_HINT;
        el.arHint.classList.add('show');
    }
    function hideHint() {
        if (!el.arHint) return;
        el.arHint.classList.remove('show');
    }
    // 搬迁说明（同一个 .ar-hint 样式，出错才显示的规则不适用于它：空态说明常驻）
    function setHint(node, text, kind) {
        if (!node) return;
        node.textContent = text || '';
        node.classList.remove('show');
        if (text) node.classList.add('show');
        if (kind) node.classList.add('is-' + kind);
    }

    function setStatus(node, text, kind) {
        if (!node) return;
        node.textContent = text || '';
        node.classList.remove('is-ok', 'is-error', 'is-warn');
        if (kind) node.classList.add('is-' + kind);
    }

    function cleanBase(value) {
        return String(value || '').trim().replace(/\/+$/, '');
    }

    function humanBytes(value) {
        var n = Number(value || 0);
        if (!n) return '—';
        var units = ['B', 'KB', 'MB', 'GB', 'TB'];
        var i = 0;
        while (n >= 1024 && i < units.length - 1) { n = n / 1024; i += 1; }
        return (i === 0 ? n : n.toFixed(1)) + ' ' + units[i];
    }

    function sourceLabel(source) {
        if (source === 'custom') return '已自定义';
        if (source === 'installer') return '安装时指定';
        if (source === 'env') return '环境变量指定';
        return '系统默认';
    }

    async function resolveBase() {
        if (state.base) return state.base;
        try {
            var response = await fetch('/static/app_config.json?v=' + Date.now(), { cache: 'no-store' });
            var config = await response.json();
            state.base = cleanBase((config && config.proxy && config.proxy.base_url) || '') || DEFAULT_BASE;
        } catch (_) {
            state.base = DEFAULT_BASE;
        }
        return state.base;
    }

    async function api(path, options) {
        var base = await resolveBase();
        var response = await fetch(base + path, Object.assign({
            headers: { 'Content-Type': 'application/json' }
        }, options || {}));
        var text = await response.text();
        var payload = null;
        try { payload = JSON.parse(text); } catch (_) { payload = null; }
        if (!response.ok) {
            var detail = (payload && (payload.detail || payload.error)) || ('HTTP ' + response.status);
            throw new Error(detail);
        }
        return payload || {};
    }

    function render() {
        var data = state.data;
        if (!data) return;
        el.arCurrentDir.textContent = data.assets_dir || '—';
        el.arSourceTag.textContent = sourceLabel(data.source);
        el.arSourceTag.classList.toggle('is-custom', data.source === 'custom' || data.source === 'installer');
        if (!el.arInput.value) el.arInput.value = data.assets_dir || '';

        var meta = [];
        meta.push('可用空间 ' + humanBytes(data.free_bytes));
        if (data.source === 'default') meta.push('系统默认位置：' + data.default_dir);
        if (data.layout_missing && data.layout_missing.length) {
            meta.push('待补子目录：' + data.layout_missing.join(' / '));
        }
        el.arMeta.textContent = meta.join('　·　');

        // 待生效：收敛「重启后生效」×3 为单独一个 amber pill
        if (data.pending_restart) {
            el.arPendingPill.textContent = '已保存为 ' + (data.saved_dir || data.assets_dir) + '，重启后生效';
            el.arPendingPill.classList.add('show');
        } else {
            el.arPendingPill.classList.remove('show');
        }

        // 旧目录搬迁块：常驻不消失（老王 2026-10-16：没迁移了？想更换咋办）。
        // 有旧资产才可点；没有时禁用并说明——换目录后若旧目录有内容，这里就能搬。
        el.arLegacyDir.textContent = data.legacy_dir || '—';
        var canMigrate = !!data.legacy_has_content && !data.migration.running;
        el.arMigrateBtn.disabled = !canMigrate;
        el.arMigrateBtn.textContent = data.migration.running ? '搬迁中…' : '开始搬迁';
        if (data.legacy_has_content) {
            setHint(el.arMigrateNote, '', '');
            if (!data.migration.running && (!data.migration.status || data.migration.status === 'idle')) {
                el.arMigrateProgress.textContent = '复制，不移动：旧目录原样留着，确认后可自行删除。';
            }
        } else {
            setHint(el.arMigrateNote, '旧目录（' + (data.legacy_dir || '系统默认目录') + '）暂无资产可搬。用上面的「更换」换个目录后，如果旧目录里有东西，这里就会出现可点的「开始搬迁」。', '');
            el.arMigrateProgress.textContent = '';
            el.arMigrateBar.style.width = '0%';
        }
    }

    function renderMigration(migration) {
        if (!migration) return;
        var m = migration;
        if (m.running || m.status === 'running') {
            var total = Number(m.total || 0);
            var done = Number(m.copied || 0) + Number(m.skipped || 0) + Number(m.failed || 0);
            var pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;
            el.arMigrateProgress.textContent = '搬迁中：' + done + ' / ' + total + '（已复制 ' + m.copied + '，跳过 ' + m.skipped + '，失败 ' + m.failed + '）';
            el.arMigrateBar.style.width = pct + '%';
            el.arMigrateBtn.disabled = true;
            el.arMigrateBtn.textContent = '搬迁中…';
            return;
        }
        if (m.status && m.status !== 'idle') {
            var text = '上次搬迁：已复制 ' + m.copied + '，跳过 ' + m.skipped + '，失败 ' + m.failed;
            if (m.status === 'done') text += '（完成，旧目录文件仍在原处，确认无误后可自行删除）';
            else if (m.status === 'done_with_errors') text += '（有失败项，旧文件仍在原处）';
            else if (m.status === 'failed') text += '（失败：' + (m.error || '未知原因') + '）';
            el.arMigrateProgress.textContent = text;
            el.arMigrateBar.style.width = '100%';
        }
    }

    async function refresh() {
        try {
            state.data = await api('/api/assets-root', { method: 'GET' });
            hideHint();
            render();
            renderMigration(state.data.migration);
            if (state.data.migration && state.data.migration.running) {
                schedulePoll();
            }
        } catch (error) {
            el.arCurrentDir.textContent = '读取失败';
            setStatus(el.arSaveStatus, '连不上后端：' + error.message, 'error');
        }
    }

    function schedulePoll() {
        if (state.timer) return;
        state.timer = window.setTimeout(function () {
            state.timer = null;
            refresh();
        }, 1500);
    }

    async function save(useDefault) {
        var path = useDefault ? '' : String(el.arInput.value || '').trim();
        if (!useDefault && !path) {
            showHint(RULE_HINT);
            setStatus(el.arSaveStatus, '先填一个绝对路径，或者点「恢复系统默认」。', 'warn');
            return;
        }
        el.arSaveBtn.disabled = true;
        setStatus(el.arSaveStatus, useDefault ? '正在恢复默认…' : '正在校验并创建目录…', '');
        try {
            var result = await api('/api/assets-root', {
                method: 'POST',
                body: JSON.stringify({ assets_dir: path, use_default: useDefault })
            });
            hideHint();
            var message = '已保存：' + result.assets_dir;
            if (result.created && result.created.length) message += '（新建子目录 ' + result.created.length + ' 个）';
            setStatus(el.arSaveStatus, message, 'ok');
            el.arInput.value = result.assets_dir || '';
            await refresh();
        } catch (error) {
            showHint(RULE_HINT);
            setStatus(el.arSaveStatus, error.message || '保存失败', 'error');
        } finally {
            el.arSaveBtn.disabled = false;
        }
    }

    async function migrate() {
        el.arMigrateBtn.disabled = true;
        el.arMigrateBtn.textContent = '搬迁中…';
        try {
            await api('/api/assets-root/migrate', {
                method: 'POST',
                body: JSON.stringify({})
            });
            setStatus(el.arMigrateProgress, '已开始搬迁，正在后台复制…', '');
            schedulePoll();
        } catch (error) {
            setStatus(el.arMigrateProgress, error.message || '搬迁失败', 'error');
            el.arMigrateBtn.disabled = false;
            el.arMigrateBtn.textContent = '开始搬迁';
        }
    }

    if (el.arSaveBtn) el.arSaveBtn.addEventListener('click', function () { save(false); });
    if (el.arDefaultBtn) el.arDefaultBtn.addEventListener('click', function () { save(true); });
    if (el.arMigrateBtn) el.arMigrateBtn.addEventListener('click', function () { migrate(); });

    // 「浏览…」：iframe 里没有 chrome.webview，经父文档转发给壳层弹原生文件夹选择框
    if (el.arBrowseBtn) el.arBrowseBtn.addEventListener('click', function () {
        try {
            window.parent.postMessage({ type: 'shell-forward', msg: 'assets|pick-dir' }, '*');
            setStatus(el.arSaveStatus, '已打开文件夹选择框…', '');
        } catch (e) {
            setStatus(el.arSaveStatus, '无法打开文件夹选择框：' + e.message, 'error');
        }
    });

    // 壳层选完目录后经父文档回传
    window.addEventListener('message', function (event) {
        var data = event.data || {};
        if (data.type === 'assets-dir-picked' && data.path) {
            el.arInput.value = data.path;
            hideHint();
            setStatus(el.arSaveStatus, '已选择：' + data.path + '，点「保存并创建」生效。', 'ok');
        }
    });

    refresh();
})();
