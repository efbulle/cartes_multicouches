function applyLayerIndices(layer, indices) {
    layer.filtre.indices = indices;
    layer.src_geo.change.emit();
}
function selectedValues(widget, meta) {
    if (!widget) {
        return [];
    }
    if (meta && meta.kind === 'single') {
        return widget.value === meta.none_value ? [] : [widget.value];
    }
    return Array.isArray(widget.value) ? widget.value : [];
}
function filterValue(value, isBoolean) {
    if (!isBoolean) {
        return String(value);
    }
    if (value === true || value === 1) {
        return 'True';
    }
    if (value === false || value === 0) {
        return 'False';
    }
    return String(value);
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

const activeFilters = [];
for (const [key, widget] of Object.entries(widgets)) {
    const meta = widgetMeta ? widgetMeta[key] : null;
    const values = selectedValues(widget, meta);
    if (!values || values.length === 0) {
        continue;
    }
    const layerName = meta && meta.layer ? meta.layer : null;
    const colName = meta && meta.column ? meta.column : key.split("__").at(-1);
    if (!colName) {
        continue;
    }
    activeFilters.push({
        column: colName,
        values: new Set(values),
        layer: layerName,
    });
}

for (const [layer_name, layer] of Object.entries(layers)) {
    const data = layer.src_geo.data;
    const n = data[colIndexStr].length;
    const booleanColumns = new Set(layer.boolean_columns || []);

    const relevant_filters = [];
    for (const filterInfo of activeFilters) {
        if (filterInfo.layer && filterInfo.layer !== layer_name) {
            continue;
        }
        if (!(filterInfo.column in data)) {
            continue;
        }
        relevant_filters.push([
            data[filterInfo.column],
            filterInfo.values,
            booleanColumns.has(filterInfo.column),
        ]);
    }

    const keep = [];
    for (let i = 0; i < n; i++) {
        let row_is_valid = true;
        for (const [colvals, values, isBoolean] of relevant_filters) {
            if (!values.has(filterValue(colvals[i], isBoolean))) {
                row_is_valid = false;
                break;
            }
        }
        if (row_is_valid) {
            keep.push(i);
        }
    }

    applyLayerIndices(layer, keep);
}

if (indicatorDiv) {
    indicatorDiv.text = renderIndicators(layers);
}
