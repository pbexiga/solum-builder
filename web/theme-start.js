// The chosen theme is the server's (D-311): it is on <html> already when the page arrives.
// This is only for the first visit after the choice moved there, when the server keeps no
// preferences yet (it says so with `null`) and this browser may hold an old choice
// (View → Theme, D-303): put it on before the page draws, so it never flashes in another
// one; storage.js then hands it to the server. A plain script, run in <head> of the app
// and the guide: a module would run too late. The key and the names are theme.js's (a test
// keeps them so).
try {
  if (document.getElementById("solum-prefs")?.textContent === "null") {
    const id = JSON.parse(localStorage.getItem("solum.theme") ?? "null");
    if (id === "dark" || id === "light") document.documentElement.dataset.theme = id;
  }
} catch {
  // storage blocked or garbled: the default theme
}
