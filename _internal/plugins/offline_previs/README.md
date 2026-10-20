# 运镜动画预设插件 2.0

入口：**画布 → 新建3D预演节点 → 运镜设置**。

用户选择运镜名称，设置时长、起始景别、焦距与幅度，再生成预览视频。幅度留空自动计算。主体可选X_Bot、Y_Bot或双人；不需要填写相机XYZ、人物XYZ或瞄准坐标。

“更多”中提供平稳/匀速/渐快/渐慢、居中/左三分/右三分及结束景别。指定结束景别时，系统反算距离；未指定时距离决定结束景别。推近/拉远会随裁切范围调整瞄准高度，保留头部空间。修改焦距会重新匹配起始机距，维持所选景别。

## 已有30项资产的使用

原始 `30种摄像机运动.blend` 不覆盖。按实际求值的相机世界位置和朝向筛选，19项进入 `tygg_previs/assets/motion_cameras.blend`，11项无实际相机运动的效果从主列表移除。完整审计及源文件SHA256位于 `tygg_previs/assets/motion_catalog.json`。

保留：慢推进、摇镜揭示、中景跟拍、穿梭、超现实、希区柯克变焦、慢速拉出、上摇、下摇、水平摇镜、横移、渐进变速横移、吊臂上升、吊臂下降、第一人称行走、遮挡揭示、穿飞、窥视推进、180度环绕。画布中部分名称简化为推近、拉远、环绕、升高等。

移除：慢镜头感、背景虚化、低机位、高机位、浅景深、转移焦点、蒙太奇、冲击变焦、正反打、鱼眼镜头、前景遮挡转场。它们只有静态机位、光学变化、多机位陈列或物体移动，没有实际相机机位/朝向变化。希区柯克变焦保留，因为它包含真实推进，并配合反向变焦。

## 架构

- `web/motion.js`：简洁的画布参数面板；旧起落幅编辑器不再作为主入口。
- `plugin.py`：本地任务、取消、排队、结果适配；不调用LLM。
- `motion_previs_cli.py`：可独立运行的Blender后台入口。
- `tygg_previs/motion_model.py`：无Blender依赖的参数与预设协议。
- `tygg_previs/motion_engine.py`：约束摄像机、自动取景、视频导出和更新。
- `assets/motion_cameras.blend`：筛选后的实际摄像机资产。
- `assets/walk_actions.blend`：按X_Bot/Y_Bot绑定分别准备的现成行走循环；跟随类复用，不逐镜重做。

相机使用真实Follow Path或固定机位约束、原资产的瞄准约束，以及稳定上轴约束。相机本体没有位置/旋转动画关键帧，运动进度只有两个键。普通改参复用上次的预演工程和人物；切换预设只更新自身的相机结构，切换主体时才新建对应人物资产。

主协议：

```json
{"schema_version":"motion/1.0","preset":"02_慢推进","duration":4,"framing":"full","lens_mm":50,"amount":null,"subject":"x_bot","direction":"left","pace":"preset","composition":"center","end_framing":"auto"}
```

时长1–30秒；焦距18–135mm；幅度单位按预设自动切换为米或度。`subject`为`x_bot/y_bot/both`；`framing`为`wide/full/medium/close/detail`。完整默认值与校验由motion_model提供。

独立调用：

```text
blender --background --factory-startup --python-exit-code 1 --python motion_previs_cli.py -- --spec motion.json --output result
```

可通过 `--previous-blend` 传入上次生成的工程以复用场景。后台只允许读取同一画布输出目录内的对应工程，加载时关闭文件内脚本自动执行。

输出为 `preview.mp4`、`poster.png`、`previs.blend`、`shot.json`和`checks.json`，视频回填原节点。改参重跑遵循画布原有归档规则，不自动创建历史分组。

当前在Blender5.2.0 LTS验证。19项预设均检查了实际运动与关键帧数量；推近、横移、环绕、跟随已实际渲染；画布内生成、改参复用、播放、刷新恢复均有运行记录。采样检查不等于连续网格碰撞或成片审美认证。
