const images = [
  { colors: ["#1d3557", "#78b3ce"], sun: "#ffd166", label: "Horská krajina" },
  { colors: ["#4d2d52", "#ef8354"], sun: "#ffe8a3", label: "Západ slunce" },
  { colors: ["#264653", "#7ab896"], sun: "#f4d35e", label: "Lesní jezero" }
];

const form = document.querySelector("#test-form");
const image = document.querySelector("#test-image");
const imageNumber = document.querySelector("#image-number");
const status = document.querySelector("#status");
const nextButton = document.querySelector("#next-button");
const startButton = document.querySelector("#start-button");
const introScreen = document.querySelector("#intro-screen");
const testScreen = document.querySelector("#test-screen");
let currentIndex = 0;

function makeIllustration(item) {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 800 500">
    <defs><linearGradient id="sky" x2="0" y2="1"><stop stop-color="${item.colors[0]}"/><stop offset="1" stop-color="${item.colors[1]}"/></linearGradient></defs>
    <rect width="800" height="500" fill="url(#sky)"/>
    <circle cx="620" cy="115" r="58" fill="${item.sun}" opacity=".9"/>
    <path d="M0 390 170 205 325 370 470 160 670 370 800 260V500H0Z" fill="#172033" opacity=".72"/>
    <path d="M0 435 210 315 370 420 575 275 800 410V500H0Z" fill="#0d1728" opacity=".8"/>
    <path d="M0 430 Q210 390 400 440 T800 415V500H0Z" fill="#bcd9e8" opacity=".45"/>
  </svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function updateButtonState() {
  const hasAnswer = form.elements.answer.value !== "";
  const hasConfidence = form.elements.confidence.value !== "";
  nextButton.disabled = !(hasAnswer && hasConfidence);
  status.textContent = nextButton.disabled ? "Vyberte odpověď" : "Připraveno";
}

function showImage() {
  const item = images[currentIndex];
  image.src = makeIllustration(item);
  image.alt = `Testovací obrázek: ${item.label}`;
  imageNumber.textContent = `Obrázek ${currentIndex + 1} z ${images.length}`;
  nextButton.textContent = currentIndex === images.length - 1 ? "Dokončit test" : "Další obrázek";
  form.reset();
  updateButtonState();
}

form.addEventListener("change", updateButtonState);

form.addEventListener("submit", (event) => {
  event.preventDefault();

  if (currentIndex < images.length - 1) {
    currentIndex += 1;
    showImage();
  } else {
    imageNumber.textContent = "Test dokončen";
    status.textContent = "Děkujeme";
    form.innerHTML = '<p class="intro">Vaše odpovědi byly zaznamenány pouze v rámci této ukázky. Děkujeme za účast.</p>';
  }
});

startButton.addEventListener("click", () => {
  introScreen.classList.add("is-hidden");
  testScreen.classList.remove("is-hidden");
  showImage();
});
