tables.visible = !tables.visible;

if (plot && plot.reset) {
	plot.reset.emit();
}
