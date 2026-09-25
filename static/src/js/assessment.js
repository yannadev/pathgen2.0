const revealActivityQuestion = (content, fallbackButton) => {
  content.hidden = false;
  fallbackButton?.setAttribute("hidden", "");
  content.querySelector("h2")?.focus();
};

const installYouTubeApi = () => {
  if (window.YT?.Player) return Promise.resolve(window.YT);
  if (window.pathgenYouTubeApi) return window.pathgenYouTubeApi;

  window.pathgenYouTubeApi = new Promise((resolve) => {
    const previousReady = window.onYouTubeIframeAPIReady;
    window.onYouTubeIframeAPIReady = () => {
      previousReady?.();
      resolve(window.YT);
    };
    const script = document.createElement("script");
    script.src = "https://www.youtube.com/iframe_api";
    document.head.appendChild(script);
  });
  return window.pathgenYouTubeApi;
};

const initializeActivityCue = async (container) => {
  const iframe = container.querySelector("[data-youtube-player]");
  const content = document.querySelector("[data-video-question-content]");
  const fallbackButton = container.querySelector("[data-reveal-video-question]");
  const cue = Number.parseFloat(container.dataset.videoCue || "");
  if (!iframe || !content || !Number.isFinite(cue)) return;

  content.hidden = true;
  fallbackButton?.removeAttribute("hidden");
  fallbackButton?.addEventListener("click", () => revealActivityQuestion(content, fallbackButton));

  try {
    const YT = await installYouTubeApi();
    let cueReached = false;
    let timer;
    const player = new YT.Player(iframe, {
      events: {
        onStateChange(event) {
          window.clearInterval(timer);
          if (event.data !== YT.PlayerState.PLAYING || cueReached) return;
          timer = window.setInterval(() => {
            if (player.getCurrentTime() < cue) return;
            cueReached = true;
            window.clearInterval(timer);
            player.pauseVideo();
            revealActivityQuestion(content, fallbackButton);
          }, 250);
        },
      },
    });
  } catch (_error) {
    revealActivityQuestion(content, fallbackButton);
  }
};

document.addEventListener("DOMContentLoaded", () => {
  document.querySelectorAll("[data-video-question]").forEach(initializeActivityCue);
  document.querySelector("[data-assessment-feedback]")?.focus();
});
