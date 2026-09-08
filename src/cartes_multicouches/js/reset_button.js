function fullRangeIndices(n) {
    return Array.from({ length: n }, (_, i) => i);
}
function applyLayerIndices(layer, indices) {
    layer.filtre.indices = indices;
    layer.src_geo.change.emit();
}
function resetWidget(widget, meta) {
    if (meta && meta.kind === 'single') {
        widget.value = meta.none_value;
    } else {
        widget.value = [];
    }
}
function formatNumber(value) {
    return new Intl.NumberFormat('fr-FR', { maximumFractionDigits: 2 }).format(value);
}
function sumColumn(values, indices) {
    let total = 0;
    for (const index of indices) {
        const numericValue = Number(values[index]);
        if (Number.isFinite(numericValue)) {
            total += numericValue;
        }
    }
    return total;
}
function renderIndicators(layers) {
    const sections = [];
    for (const [layerName, layer] of Object.entries(layers)) {
        const specs = layer.indicators || [];
        if (!specs.length) {
            continue;
        }
        const data = layer.src_geo.data;
        const filteredIndices = layer.filtre.indices || [];
        const rows = specs.map((spec) => {
            const total = Number(spec.total) || 0;
            const filtered = spec.kind === 'count'
                ? filteredIndices.length
                : (spec.column && data[spec.column] !== undefined)
                    ? sumColumn(data[spec.column], filteredIndices)
                    : 0;
            return `<div style='margin:1px 0;'>${spec.label} : <b>${formatNumber(filtered)}</b> / ${formatNumber(total)}</div>`;
        }).join('');
        sections.push(`<div style='margin-top:6px;'><div style='font-weight:600;'>${layerName}</div>${rows}</div>`);
    }
    if (!sections.length) {
        return '';
    }
    return `<div style='font-weight:bold; margin-bottom:4px;'>Indicateurs</div>${sections.join('')}`;
}

for (const [key, widget] of Object.entries(widgets)) {
    resetWidget(widget, widgetMeta ? widgetMeta[key] : null);
}
layer_widget.active = default_active;
if (annotation_widget) {
    annotation_widget.active = default_active_annotations;
}

function annotationEnabled(layerName) {
    if (!annotation_widget) {
        return true;
    }
    const idx = annotation_labels.indexOf(layerName);
    if (idx < 0) {
        return false;
    }
    const activeAnn = Array.isArray(annotation_widget.active) ? annotation_widget.active : [];
    return activeAnn.includes(idx);
}

for (const layerName of layer_labels) {
    const isLayerVisible = default_active.includes(layer_labels.indexOf(layerName));

    const geom = geometry_renderers[layerName];
    if (geom) {
        geom.visible = isLayerVisible;
    }

    const ann = annotation_renderers[layerName];
    if (ann) {
        ann.visible = isLayerVisible && annotationEnabled(layerName);
    }
}
for (const layer of Object.values(layers)) {
    const n = layer.src_geo.data[colIndexStr].length;
    applyLayerIndices(layer, fullRangeIndices(n));
}

if (indicatorDiv) {
    indicatorDiv.text = renderIndicators(layers);
}
