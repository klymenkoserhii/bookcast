/* Shared chapter audio loading; classic script also works from file://. */
function loadReaderAudio(audio, url, onError) {
  let objectUrl = null;
  let closed = false;
  window.addEventListener("pagehide", () => {
    closed = true;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
  }, { once: true });

  if (location.protocol === "file:") {
    audio.src = url;
    audio.load();
    return;
  }

  (async () => {
    try {
      const response = await fetch(url);
      if (!response.ok) throw new Error(`Audio request failed (${response.status})`);
      const blob = await response.blob();
      if (closed) return;
      objectUrl = URL.createObjectURL(blob);
      audio.src = objectUrl;
      audio.load();
    } catch (error) {
      console.error("Could not load chapter audio:", error);
      onError();
    }
  })();
}
