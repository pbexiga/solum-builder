// Puts the theme this browser last chose (View → Theme, D-303) on the page before it draws,
// so it never flashes in another one. A plain script, run in <head> of the app and the guide:
// a module would run too late. The key and the names are theme.js's (a test keeps them so).
try {
  const id = JSON.parse(localStorage.getItem("solum.theme") ?? "null");
  if (id === "dark" || id === "light") document.documentElement.dataset.theme = id;
} catch {
  // storage blocked or garbled: the default theme
}
