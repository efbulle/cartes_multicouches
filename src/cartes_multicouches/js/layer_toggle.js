function annotationEnabled(layerName) {
    if (!annotationWidget) {
        return true;
    }
    const idx = annotationLabels.indexOf(layerName);
    if (idx < 0) {
        return false;
    }
    const activeAnn = Array.isArray(annotationWidget.active) ? annotationWidget.active : [];
    return activeAnn.includes(idx);
}

const active = Array.isArray(cb_obj.active) ? cb_obj.active : [];
for (let i = 0; i < layerLabels.length; i++) {
    const layerName = layerLabels[i];
    const isLayerVisible = active.includes(i);

    const geom = geometryRenderers[layerName];
    if (geom) {
        geom.visible = isLayerVisible;
    }

    const ann = annotationRenderers[layerName];
    if (ann) {
        ann.visible = isLayerVisible && annotationEnabled(layerName);
    }
}
