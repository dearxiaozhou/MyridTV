/* Pure rectangle calculations shared by crop and outpaint editing. */
(function(global){
    'use strict';

    function clampCrop(rect, bounds, minimum=24){
        const width = Math.max(minimum, Math.min(rect.w, bounds.w));
        const height = Math.max(minimum, Math.min(rect.h, bounds.h));
        return {
            ...rect,
            w:width,
            h:height,
            x:Math.max(0, Math.min(rect.x, bounds.w - width)),
            y:Math.max(0, Math.min(rect.y, bounds.h - height))
        };
    }

    function clampOutpaint(rect, bounds){
        const width = Math.max(bounds.w, rect.w);
        const height = Math.max(bounds.h, rect.h);
        return {
            ...rect,
            w:width,
            h:height,
            x:Math.min(width - bounds.w, Math.max(0, rect.x)),
            y:Math.min(height - bounds.h, Math.max(0, rect.y))
        };
    }

    function resetRect(bounds, mode='crop'){
        if(mode === 'outpaint') return {x:0, y:0, w:bounds.w, h:bounds.h};
        return {
            x:Math.round(bounds.w * 0.08),
            y:Math.round(bounds.h * 0.08),
            w:Math.round(bounds.w * 0.84),
            h:Math.round(bounds.h * 0.84)
        };
    }

    function resizeOutpaint(start, mode, dx, dy, bounds){
        let growX = 0, growY = 0;
        if(mode === 'outpaint-left') growX = -dx;
        else if(mode === 'outpaint-right') growX = dx;
        else if(mode === 'outpaint-top') growY = -dy;
        else if(mode === 'outpaint-bottom') growY = dy;
        else if(mode === 'outpaint-corner'){growX = dx; growY = dy;}
        const width = Math.max(bounds.w, start.w + growX * 2);
        const height = Math.max(bounds.h, start.h + growY * 2);
        return clampOutpaint({
            ...start,
            w:width,
            h:height,
            x:start.x + Math.round((width - start.w) / 2),
            y:start.y + Math.round((height - start.h) / 2)
        }, bounds);
    }

    global.CanvasImageEditCropGeometryModel = {clampCrop, clampOutpaint, resetRect, resizeOutpaint};
})(typeof window !== 'undefined' ? window : globalThis);
