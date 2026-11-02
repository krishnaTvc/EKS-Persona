'use strict';
const form = document.querySelector('#registration-form');
const submit = document.querySelector('#submit-button');
const statusText = document.querySelector('#status');
const storageKey = 'wildly-you-registration';
const cast = [
  ['panda', 'Panda', 'The calm one'], ['fox', 'Fox', 'The clever one'],
  ['owl', 'Owl', 'The night thinker'], ['lion', 'Lion', 'The born leader'],
  ['cat', 'Cat', 'The free spirit'], ['dog', 'Dog', 'The team player'],
  ['rabbit', 'Rabbit', 'The side-project pro'], ['koala', 'Koala', 'The balance keeper'],
];

for (const [slug, name, tagline] of cast) {
  const card = document.createElement('div');
  card.className = 'cast-card';
  const img = document.createElement('img');
  img.src = `/media/${slug}.svg`;
  img.alt = `${name} illustration`;
  img.loading = 'lazy';
  const title = document.createElement('strong');
  title.textContent = name;
  const text = document.createElement('span');
  text.textContent = tagline;
  card.append(img, title, text);
  document.querySelector('#cast-grid').append(card);
}

function saveId(id) {
  try { localStorage.setItem(storageKey, id); } catch (_) { /* Private browsing can disable storage. */ }
}
function forgetId() {
  try { localStorage.removeItem(storageKey); } catch (_) { /* Storage is optional. */ }
}
function renderResult(data) {
  document.querySelector('#empty-result').hidden = true;
  document.querySelector('#filled-result').hidden = false;
  document.querySelector('#match-label').textContent = `${data.name}, meet your inner…`;
  document.querySelector('#animal-name').textContent = data.persona.animal;
  document.querySelector('#animal-description').textContent = data.persona.description;
  document.querySelector('#saved-details').textContent = `${data.name} · Age ${data.age}`;
  const image = document.querySelector('#animal-image');
  image.src = data.image_url;
  image.alt = `${data.persona.animal} animal persona illustration`;
  saveId(data.registration_id);
}
async function api(path, options = {}) {
  const response = await fetch(path, {...options, signal: AbortSignal.timeout(30000)});
  if (!response.ok) {
    if (response.status === 429) throw new Error('A few too many requests. Please wait a minute and try again.');
    const error = await response.json().catch(() => ({}));
    throw new Error(typeof error.detail === 'string' ? error.detail : 'Please check your name and age, then try again.');
  }
  return response.json();
}

let userInteracted = false;
form.addEventListener('input', () => { userInteracted = true; });
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  userInteracted = true;
  const name = form.elements.name.value.trim();
  const age = Number(form.elements.age.value);
  if (!name || !Number.isInteger(age) || age < 1 || age > 120) {
    statusText.textContent = 'Enter your name and an age between 1 and 120.';
    return;
  }
  submit.disabled = true;
  statusText.textContent = 'Finding your wild side…';
  try {
    const data = await api('/api/registrations', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({name, age}),
    });
    renderResult(data);
    statusText.textContent = 'Your match is saved. Refreshing will bring it back.';
  } catch (error) {
    statusText.textContent = error.name === 'TimeoutError' ? 'The app took too long. Please try again in a moment.' : error.message;
  } finally {
    submit.disabled = false;
  }
});

document.querySelector('#new-person').addEventListener('click', () => {
  userInteracted = true;
  forgetId();
  form.reset();
  document.querySelector('#empty-result').hidden = false;
  document.querySelector('#filled-result').hidden = true;
  statusText.textContent = '';
  form.elements.name.focus();
});

(async function restore() {
  let id;
  try { id = localStorage.getItem(storageKey); } catch (_) { return; }
  if (!id) return;
  try {
    const data = await api(`/api/registrations/${encodeURIComponent(id)}`);
    if (userInteracted) return;
    renderResult(data);
    form.elements.name.value = data.name;
    form.elements.age.value = data.age;
    statusText.textContent = 'Welcome back. Your saved match is right here.';
  } catch (_) {
    if (!userInteracted) statusText.textContent = 'Your previous result could not be loaded. You can try again or create a new match.';
  }
})();
