function table_to_csv(source, cols, float_cols, indices) {
    const lines = [cols.join(';')];
    const floatCols = new Set(float_cols);
    const rowIndices = Array.isArray(indices) ? indices : [];
    for (const i of rowIndices) {
        const row = cols.map((col) => {
            const column_data = source.data[col];
            if (column_data === undefined) {
                console.error('export_csv: colonne absente de source.data ->', col);
                return '';
            }
            const val = column_data[i];
            const text = val === null || val === undefined ? '' : val.toString();
            return floatCols.has(col) ? text.replace('.', ',') : text;
        });
        lines.push(row.join(';'));
    }
    return lines.join('\n').concat('\n');
}

const filetext = table_to_csv(source, cols, float_cols, filtre.indices);
const blob = new Blob(['\ufeff' + filetext], { type: 'text/csv;charset=utf-8;' });
const link = document.createElement('a');
link.href = URL.createObjectURL(blob);
link.download = filename;
link.target = '_blank';
link.style.visibility = 'hidden';
document.body.appendChild(link);
link.dispatchEvent(new MouseEvent('click'));
document.body.removeChild(link);
