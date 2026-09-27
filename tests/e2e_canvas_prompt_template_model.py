# -*- coding: utf-8 -*-
"""Browser regression for local prompt-template state and data mapping."""
import json
import sys
import urllib.request

from playwright.sync_api import sync_playwright


import os

BASE = os.environ.get("MYRIDTV_TEST_BASE", "http://127.0.0.1:3217")
VERSION = json.loads(urllib.request.urlopen(BASE + "/health", timeout=10).read())["version"]
results = []


def check(name, ok, detail=""):
    results.append(bool(ok))
    print(("PASS" if ok else "FAIL") + " - " + name + (" | " + str(detail)[:220] if detail else ""))


with sync_playwright() as pw:
    browser = pw.chromium.launch(
        executable_path=r"C:\Users\77972\AppData\Local\ms-playwright\chromium-1228\chrome-win64\chrome.exe",
        headless=True,
        args=["--no-sandbox"],
    )
    page = browser.new_page(viewport={"width": 1680, "height": 980})
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    page.add_init_script("""(() => {
      localStorage.setItem('smart_canvas_prompt_presets_v1', JSON.stringify([
        {id:'local-template',name:'本地模板',text:'本地正文',category:'custom'},
        {id:'invalid-template',name:'坏数据',text:7}
      ]));
      localStorage.setItem('smart_canvas_prompt_template_groups_v1', JSON.stringify([
        {id:'view',name:'自定义视图组',customized:true}, {id:'custom',name:'自定义分组'}
      ]));
      localStorage.setItem('smart_canvas_prompt_template_overrides_v1', JSON.stringify({
        hiddenBuiltinIds:['hidden-built-in'],
        editedBuiltins:{'visible-built-in':{name:'覆盖后的名称',positive:'覆盖后的正文',category:'custom'}}
      }));
    })();""")
    page.route("**/static/app_config.json*", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"proxy": {"base_url": BASE}})))
    page.route("**/api/prompt-libraries", lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps({
            "ok": True,
            "library": {"libraries": [{
                "id": "system", "name": "系统提示词库", "readonly": True,
                "items": [
                    {"id": "hidden-built-in", "name": "隐藏内置模板", "category": "view", "positive": "不应显示"},
                    {"id": "visible-built-in", "name": "原始内置模板", "category": "view", "positive": "原始正文"},
                ]
            }]}
        })))
    page.goto(BASE + "/smart-canvas.html?v=" + VERSION, wait_until="domcontentloaded")
    page.wait_for_timeout(1700)

    state = page.evaluate("""() => {
      const templates=promptTemplateItems();
      const groupIds=activePromptTemplateGroups().map(group=>group.id);
      return {
        module:typeof CanvasPromptTemplateModel==='object',
        presets:promptPresets.map(item=>item.id),
        templates:templates.map(item=>({id:item.id,name:item.name,positive:item.positive,category:item.category})),
        groupIds, customLabel:promptTemplateCategoryLabel('custom'), viewLabel:promptTemplateCategoryLabel('view')
      };
    }""")
    check("独立模型加载并兼容已有本地预设数据", state["module"] and state["presets"] == ["local-template"], state)
    check("内置隐藏、覆盖和本地预设映射保持正确", [item["id"] for item in state["templates"]] == ["visible-built-in", "mine:local-template"] and state["templates"][0]["name"] == "覆盖后的名称" and state["templates"][0]["positive"] == "覆盖后的正文", state["templates"])
    check("默认分组、自定义分组合并且标签沿用本地命名", "view" in state["groupIds"] and "custom" in state["groupIds"] and state["customLabel"] == "自定义分组" and state["viewLabel"] == "自定义视图组", {"groups":state["groupIds"],"labels":[state["customLabel"],state["viewLabel"]]})

    page.once("dialog", lambda dialog: dialog.accept("重命名后的视图组"))
    renamed = page.evaluate("""async () => {
      await renamePromptTemplateGroup('view');
      return {label:promptTemplateCategoryLabel('view'),stored:JSON.parse(localStorage.getItem('smart_canvas_prompt_template_groups_v1')).find(group=>group.id==='view')};
    }""")
    check("内置分类重命名更新显示并持久化", renamed["label"] == "重命名后的视图组" and renamed["stored"].get("customized") is True, renamed)

    persisted = page.evaluate("""() => {
      promptPresets.push({id:'persisted-check',text:'保留记录'});
      promptTemplateGroups.push({id:'persisted-group',name:'保留分组'});
      promptTemplateOverrides.hiddenBuiltinIds.push('persisted-hidden');
      savePromptPresets(); savePromptTemplateGroups(); savePromptTemplateOverrides();
      return {
        presets:JSON.parse(localStorage.getItem('smart_canvas_prompt_presets_v1')),
        groups:JSON.parse(localStorage.getItem('smart_canvas_prompt_template_groups_v1')),
        overrides:JSON.parse(localStorage.getItem('smart_canvas_prompt_template_overrides_v1'))
      };
    }""")
    check("写回沿用既有预设存储键和记录结构", any(item["id"] == "persisted-check" for item in persisted["presets"]), persisted["presets"])
    check("分组与内置覆盖写回对应的既有存储键", any(group["id"] == "persisted-group" for group in persisted["groups"]) and "persisted-hidden" in persisted["overrides"]["hiddenBuiltinIds"], {"groups":len(persisted["groups"]),"hidden":persisted["overrides"]["hiddenBuiltinIds"]})

    legacy = page.evaluate("""() => {
      const node={id:'legacy-preset-node',type:'smart-image',x:520,y:380,w:320,h:220,text:'旧面板初始正文',images:[]};
      nodes.push(node); render();
      const preset=createPromptPresetFromNode(node,{openPanel:true});
      return {id:preset.id,open:promptPresetPanel.classList.contains('open'),selected:promptPresetSelect.value};
    }""")
    check("旧预设面板沿用共享新增接口", legacy["open"] and legacy["selected"] == legacy["id"], legacy)
    page.locator("#promptPresetName").fill("旧面板更新名称")
    page.locator("#promptPresetText").fill("旧面板更新正文")
    page.locator("#promptPresetSave").click()
    updated_legacy = page.evaluate("""() => ({
      preset:currentPromptPreset(promptPresetSelect.value),
      template:promptTemplateItems().find(item=>item.id==='mine:'+promptPresetSelect.value),
      nodeText:nodes.find(node=>node.id==='legacy-preset-node')?.text||''
    })""")
    check("旧面板修改同步到模板库映射和关联节点", updated_legacy["preset"]["name"] == "旧面板更新名称" and updated_legacy["template"]["positive"] == "旧面板更新正文" and updated_legacy["nodeText"] == "旧面板更新正文", updated_legacy)
    page.locator("#promptPresetApply").click()
    applied_legacy = page.evaluate("""() => ({
      panelOpen:promptPresetPanel.classList.contains('open'),
      node:nodes.find(item=>item.id==='legacy-preset-node')
    })""")
    check("旧面板应用操作保持关联并正常收起", not applied_legacy["panelOpen"] and applied_legacy["node"]["promptPresetId"] == legacy["id"] and applied_legacy["node"]["text"] == "旧面板更新正文", {"open":applied_legacy["panelOpen"],"presetId":applied_legacy["node"]["promptPresetId"],"text":applied_legacy["node"]["text"]})
    page.evaluate(f"openPromptPresetPanel('legacy-preset-node','{legacy['id']}')")
    page.locator("#promptPresetDelete").click()
    page.locator("#promptPresetDelete").click()
    deleted_legacy = page.evaluate("""() => ({
      exists:promptPresets.some(item=>item.id==='""" + legacy["id"] + """'),
      linked:nodes.find(item=>item.id==='legacy-preset-node')?.promptPresetId||''
    })""")
    check("旧面板二次确认删除并清除节点引用", not deleted_legacy["exists"] and not deleted_legacy["linked"], deleted_legacy)

    lifecycle = page.evaluate("""() => {
      CanvasPromptTemplateModel.addPreset({id:'shared-crud',name:'原名称',text:'初始文本'});
      CanvasPromptTemplateModel.updatePreset('shared-crud',{name:'更新名称',text:'更新文本'});
      const removed=CanvasPromptTemplateModel.removePreset('shared-crud');
      return {removed:removed?.name,stillPresent:promptPresets.some(item=>item.id==='shared-crud'),stored:JSON.parse(localStorage.getItem('smart_canvas_prompt_presets_v1')).some(item=>item.id==='shared-crud')};
    }""")
    check("新旧预设面板共用的新增/修改/删除接口同步持久化", lifecycle["removed"] == "更新名称" and not lifecycle["stillPresent"] and not lifecycle["stored"], lifecycle)
    check("本地模型交互无页面脚本异常", not errors, errors[:2])
    browser.close()

print(f"\nRESULT: {sum(results)}/{len(results)}")
sys.exit(0 if all(results) else 1)
