// Sélectionne ou vide toutes les options d'un MultiSelect.
// Args attendus (injectés via CustomJS.from_file) : select (MultiSelect), mode ("all" | "none").
if (mode === "all") {
    select.value = select.options.map((o) => Array.isArray(o) ? o[0] : o);
} else {
    select.value = [];
}
select.change.emit();
