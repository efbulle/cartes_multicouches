function layerEnabled(layerName) {
    const idx = layerLabels.indexOf(layerName);
    if (idx < 0) {
        return false;
    }
    const activeLayers = Array.isArray(layerWidget.active) ? layerWidget.active : [];
    return activeLayers.includes(idx);
}

const activeAnnotations = Array.isArray(annotationWidget.active) ? annotationWidget.active : [];
for (let i = 0; i < annotationLabels.length; i++) {
    const layerName = annotationLabels[i];
    const ann = annotationRenderers[layerName];
    if (!ann) {
        continue;
    }
    ann.visible = layerEnabled(layerName) && activeAnnotations.includes(i);
}
