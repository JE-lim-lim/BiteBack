const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let foods = [];
let statsData = {};
let selectedDays = 3;
let editingFoodId = null;
let toastTimer;

// BiteBack-styled replacement for the browser's default confirm() popup.
function showConfirmDialog({title, message, food, eyebrow='QUICK CONFIRMATION', icon='✓', confirmLabel='Confirm', danger=false}) {
  const backdrop = $('#confirmBackdrop');
  const accept = $('#confirmAccept');
  const cancel = $('#confirmCancel');
  $('#confirmTitle').textContent = title;
  $('#confirmMessage').textContent = message;
  $('#confirmEyebrow').textContent = eyebrow;
  $('#confirmIcon').textContent = icon;
  accept.textContent = confirmLabel;
  accept.classList.toggle('is-danger', danger);
  const foodBox = $('#confirmFood');
  if (food) {
    $('#confirmFoodEmoji').textContent = foodEmoji(food.name, food.category);
    $('#confirmFoodName').textContent = food.name;
    $('#confirmFoodMeta').textContent = `${food.quantity} ${food.unit || 'item'} · ${food.category || 'Other'}`;
    foodBox.hidden = false;
  } else {
    foodBox.hidden = true;
  }
  backdrop.classList.add('open');
  backdrop.setAttribute('aria-hidden', 'false');
  document.body.classList.add('dialog-open');
  accept.focus();
  return new Promise(resolve => {
    let settled = false;
    const finish = value => {
      if (settled) return;
      settled = true;
      backdrop.classList.remove('open');
      backdrop.setAttribute('aria-hidden', 'true');
      document.body.classList.remove('dialog-open');
      accept.removeEventListener('click', onAccept);
      cancel.removeEventListener('click', onCancel);
      backdrop.removeEventListener('click', onBackdrop);
      document.removeEventListener('keydown', onKeydown);
      resolve(value);
    };
    const onAccept = () => finish(true);
    const onCancel = () => finish(false);
    const onBackdrop = e => { if (e.target === backdrop) finish(false); };
    const onKeydown = e => { if (e.key === 'Escape') finish(false); };
    accept.addEventListener('click', onAccept);
    cancel.addEventListener('click', onCancel);
    backdrop.addEventListener('click', onBackdrop);
    document.addEventListener('keydown', onKeydown);
  });
}

const foodEmoji = (name, category) => {
  const n = (name || '').toLowerCase();
  if (/egg/.test(n)) return '🥚';
  if (/banana/.test(n)) return '🍌';
  if (/spinach|leaf|kale|lettuce/.test(n)) return '🥬';
  if (/rice/.test(n)) return '🍚';
  if (/tofu/.test(n)) return '🧈';
  if (/milk/.test(n)) return '🥛';
  if (/bread/.test(n)) return '🍞';
  if (/tomato/.test(n)) return '🍅';
  if (/apple/.test(n)) return '🍎';
  if (/chicken/.test(n)) return '🍗';
  if (/fish/.test(n)) return '🐟';
  if (/potato/.test(n)) return '🥔';
  if (/carrot/.test(n)) return '🥕';
  if (/noodle|pasta/.test(n)) return '🍜';
  if (category === 'Fruit') return '🍊';
  if (category === 'Vegetables') return '🥦';
  if (category === 'Protein') return '🥚';
  if (category === 'Grains') return '🌾';
  if (category === 'Dairy') return '🥛';
  return '🥗';
};
const money = (v) => Number(v || 0).toFixed(2);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const formatDate = (value) => {
  if (!value) return 'No date set';
  const d = new Date(value + 'T00:00:00');
  return Number.isNaN(d.getTime()) ? value : d.toLocaleDateString(undefined, {day:'numeric',month:'short'});
};
const daysLabel = (days) => {
  if (days === null || days === undefined) return 'No expiry date';
  if (days < 0) return `Past date by ${Math.abs(days)}d`;
  if (days === 0) return 'Date is today';
  if (days === 1) return '1 day left';
  return `${days} days left`;
};
const urgencyLabel = (urgency) => ({urgent:'Use soon',soon:'Coming up',overdue:'Check date',ok:'In good time',unknown:'No date'}[urgency] || 'No date');

async function api(url, options={}) {
  const response = await fetch(url, {
    headers: {'Content-Type':'application/json', ...(options.headers || {})},
    ...options
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.error || 'Something went wrong. Please try again.');
  return data;
}
function toast(message) {
  const el = $('#toast');
  el.textContent = message;
  el.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove('show'), 3000);
}
function navigate(view) {
  $$('.page').forEach(p => p.classList.toggle('active', p.id === `view-${view}`));
  $$('.nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === view));
  const labels = {overview:'Overview', pantry:'My Pantry', budget:'Budget Rescue', impact:'My Impact'};
  $('#breadcrumbTitle').textContent = labels[view] || 'Overview';
  if (view === 'pantry') renderPantry();
  if (view === 'impact') renderImpact();
  window.scrollTo({top:0,behavior:'smooth'});
}
$$('.nav-item').forEach(btn => btn.addEventListener('click', () => navigate(btn.dataset.view)));
$$('[data-go]').forEach(btn => btn.addEventListener('click', () => navigate(btn.dataset.go)));
$('#todayLabel').textContent = new Date().toLocaleDateString(undefined,{weekday:'short',month:'short',day:'numeric'});
$('#refreshBtn').addEventListener('click', refreshAll);

async function refreshAll() {
  try {
    const [foodResult, statResult] = await Promise.all([api('/api/foods'), api('/api/stats')]);
    foods = foodResult.foods || [];
    statsData = statResult;
    renderOverview();
    renderPantry();
    renderImpact();
  } catch (err) {
    toast(err.message);
  }
}
function urgencyClass(food) {
  return ['urgent','soon','overdue','ok'].includes(food.urgency) ? food.urgency : 'ok';
}
function renderOverview() {
  $('#statPantry').textContent = statsData.active_foods ?? foods.length;
  $('#statUrgent').innerHTML = `${statsData.urgent_foods ?? 0} <small>items</small>`;
  $('#statSaved').textContent = money(statsData.estimated_value_used_rm);
  $('#statWasted').textContent = money(statsData.estimated_value_wasted_rm);
  $('#navFoodCount').textContent = foods.length;
  const priority = [...foods].sort((a,b) => {
    const av = a.days_left == null ? 999 : a.days_left;
    const bv = b.days_left == null ? 999 : b.days_left;
    return av - bv;
  }).slice(0,4);
  $('#urgentFoods').innerHTML = priority.length ? priority.map(f => `
    <div class="food-row">
      <div class="food-emoji">${foodEmoji(f.name,f.category)}</div>
      <div class="food-info"><strong>${esc(f.name)}</strong><small>${esc(f.quantity)} ${esc(f.unit)} · ${esc(f.category)}</small></div>
      <div class="food-date"><span class="pill ${urgencyClass(f)}">${urgencyLabel(f.urgency)}</span><small>${esc(daysLabel(f.days_left))}</small></div>
    </div>`).join('') : '<div class="empty-state">Your pantry is empty. Add an ingredient to get started.</div>';
  renderActivities('#recentActivity', statsData.recent_events || []);
}
function renderPantry() {
  if (!$('#pantryGrid')) return;
  const query = ($('#foodSearch')?.value || '').trim().toLowerCase();
  const category = $('#categoryFilter')?.value || 'all';
  const sort = $('#sortFilter')?.value || 'expiry';
  let list = foods.filter(f => f.name.toLowerCase().includes(query) && (category === 'all' || f.category === category));
  list.sort((a,b) => sort === 'name' ? a.name.localeCompare(b.name) : (a.days_left ?? 999) - (b.days_left ?? 999));
  $('#pantryGrid').innerHTML = list.length ? list.map(f => `
    <article class="pantry-card">
      <div class="pantry-card-top"><div class="food-emoji">${foodEmoji(f.name,f.category)}</div><span class="pill ${urgencyClass(f)}">${urgencyLabel(f.urgency)}</span></div>
      <h3>${esc(f.name)}</h3><div class="pantry-meta">${esc(f.quantity)} ${esc(f.unit)} · ${esc(f.category)}</div>
      <div class="pantry-expiry"><small>${f.expiry_date ? `Best-before: ${esc(formatDate(f.expiry_date))}` : 'No date recorded'}</small><strong>RM ${money(f.estimated_value)}</strong></div>
      <div class="pantry-card-actions"><button class="outline-button" data-edit-food="${f.id}">Edit ingredient</button><button class="outline-button" data-delete-food="${f.id}">Delete</button><button class="outline-button" data-food-event="${f.id}" data-event="used">✓ Mark used</button><button class="outline-button" data-food-event="${f.id}" data-event="wasted">↗ Mark wasted</button></div>
    </article>`).join('') : '<div class="empty-state" style="grid-column:1/-1">No ingredients match. Add an ingredient or change your filters.</div>';
  $$('[data-food-event]').forEach(btn => btn.addEventListener('click', () => recordFoodEvent(btn.dataset.foodEvent, btn.dataset.event)));
  $$('[data-edit-food]').forEach(btn => btn.addEventListener('click', () => openEditModal(btn.dataset.editFood)));
  $$('[data-delete-food]').forEach(btn => btn.addEventListener('click', () => deleteFood(btn.dataset.deleteFood)));
}
function renderActivities(selector, events) {
  const el = $(selector);
  if (!el) return;
  el.innerHTML = events.length ? events.map(e => {
    const wasted = e.event_type === 'wasted';
    return `<div class="activity-row"><div class="activity-mark ${wasted?'wasted':''}">${wasted?'⌁':'✓'}</div><div class="activity-copy"><strong>${wasted?'Marked as wasted':'Ingredient used'}: ${esc(e.food_name)}</strong><small>${esc(e.quantity)} portion(s) · ${esc(new Date(e.created_at+'Z').toLocaleDateString(undefined,{day:'numeric',month:'short'}))}${e.note ? ' · '+esc(e.note):''}</small></div><div class="activity-value">RM ${money(e.value_rm)}</div></div>`;
  }).join('') : '<div class="empty-state">No activity yet. Mark an ingredient as used or wasted to start tracking your progress.</div>';
}
function renderImpact() {
  $('#impactSaved').textContent = money(statsData.estimated_value_used_rm);
  $('#impactUsedCount').textContent = money(statsData.items_used);
  $('#impactWastedCount').textContent = money(statsData.items_wasted);
  $('#impactWastedValue').textContent = money(statsData.estimated_value_wasted_rm);
  $('#impactActive').textContent = statsData.active_foods ?? foods.length;
  renderActivities('#impactActivity', statsData.recent_events || []);
}
const modal = $('#foodModal');
const commonIngredients = [
  {name:"Eggs",emoji:"🥚",category:"Protein",unit:"pcs"},
  {name:"Chicken",emoji:"🍗",category:"Protein",unit:"g"},
  {name:"Fish",emoji:"🐟",category:"Protein",unit:"g"},
  {name:"Prawns",emoji:"🦐",category:"Protein",unit:"g"},
  {name:"Beef",emoji:"🥩",category:"Protein",unit:"g"},
  {name:"Tofu",emoji:"🧈",category:"Protein",unit:"blocks"},
  {name:"Tempeh",emoji:"🫘",category:"Protein",unit:"g"},
  {name:"Canned tuna",emoji:"🥫",category:"Protein",unit:"can"},
  {name:"Beans",emoji:"🫘",category:"Protein",unit:"g"},
  {name:"Rice",emoji:"🍚",category:"Grains",unit:"kg"},
  {name:"Bread",emoji:"🍞",category:"Grains",unit:"loaf"},
  {name:"Noodles",emoji:"🍜",category:"Grains",unit:"pack"},
  {name:"Pasta",emoji:"🍝",category:"Grains",unit:"g"},
  {name:"Oats",emoji:"🥣",category:"Grains",unit:"g"},
  {name:"Flour",emoji:"🌾",category:"Grains",unit:"g"},
  {name:"Cereal",emoji:"🥣",category:"Grains",unit:"box"},
  {name:"Milk",emoji:"🥛",category:"Dairy",unit:"L"},
  {name:"Cheese",emoji:"🧀",category:"Dairy",unit:"g"},
  {name:"Yogurt",emoji:"🥣",category:"Dairy",unit:"cup"},
  {name:"Butter",emoji:"🧈",category:"Dairy",unit:"g"},
  {name:"Tomato",emoji:"🍅",category:"Vegetables",unit:"pcs"},
  {name:"Carrot",emoji:"🥕",category:"Vegetables",unit:"pcs"},
  {name:"Broccoli",emoji:"🥦",category:"Vegetables",unit:"pcs"},
  {name:"Spinach",emoji:"🥬",category:"Vegetables",unit:"bunch"},
  {name:"Cabbage",emoji:"🥬",category:"Vegetables",unit:"pcs"},
  {name:"Lettuce",emoji:"🥬",category:"Vegetables",unit:"head"},
  {name:"Cucumber",emoji:"🥒",category:"Vegetables",unit:"pcs"},
  {name:"Potato",emoji:"🥔",category:"Vegetables",unit:"pcs"},
  {name:"Sweet potato",emoji:"🍠",category:"Vegetables",unit:"pcs"},
  {name:"Onion",emoji:"🧅",category:"Vegetables",unit:"pcs"},
  {name:"Garlic",emoji:"🧄",category:"Vegetables",unit:"bulb"},
  {name:"Bell pepper",emoji:"🫑",category:"Vegetables",unit:"pcs"},
  {name:"Mushroom",emoji:"🍄",category:"Vegetables",unit:"g"},
  {name:"Pumpkin",emoji:"🎃",category:"Vegetables",unit:"g"},
  {name:"Corn",emoji:"🌽",category:"Vegetables",unit:"pcs"},
  {name:"Green beans",emoji:"🫛",category:"Vegetables",unit:"g"},
  {name:"Eggplant",emoji:"🍆",category:"Vegetables",unit:"pcs"},
  {name:"Bean sprouts",emoji:"🌱",category:"Vegetables",unit:"g"},
  {name:"Apple",emoji:"🍎",category:"Fruit",unit:"pcs"},
  {name:"Banana",emoji:"🍌",category:"Fruit",unit:"pcs"},
  {name:"Orange",emoji:"🍊",category:"Fruit",unit:"pcs"},
  {name:"Mango",emoji:"🥭",category:"Fruit",unit:"pcs"},
  {name:"Grapes",emoji:"🍇",category:"Fruit",unit:"bunch"},
  {name:"Watermelon",emoji:"🍉",category:"Fruit",unit:"pcs"},
  {name:"Papaya",emoji:"🍈",category:"Fruit",unit:"pcs"},
  {name:"Pineapple",emoji:"🍍",category:"Fruit",unit:"pcs"},
  {name:"Strawberry",emoji:"🍓",category:"Fruit",unit:"box"},
  {name:"Avocado",emoji:"🥑",category:"Fruit",unit:"pcs"},
  {name:"Lemon",emoji:"🍋",category:"Fruit",unit:"pcs"},
  {name:"Cooking oil",emoji:"🫒",category:"Other",unit:"ml"},
  {name:"Soy sauce",emoji:"🧂",category:"Other",unit:"ml"},
  {name:"Sugar",emoji:"🍚",category:"Other",unit:"g"},
  {name:"Salt",emoji:"🧂",category:"Other",unit:"g"},
  {name:"Peanut butter",emoji:"🥜",category:"Other",unit:"jar"},
  {name:"Coconut milk",emoji:"🥥",category:"Other",unit:"can"},
  {name:"Curry paste",emoji:"🍛",category:"Other",unit:"pack"}
];
function renderIngredientMenu(query = '') {
  const menu = $('#ingredientMenu');
  if (!menu) return;
  const q = query.trim().toLowerCase();
  const items = commonIngredients.filter(item => item.name.toLowerCase().includes(q) || item.category.toLowerCase().includes(q));
  menu.innerHTML = items.length ? items.map(item => `<button type="button" class="ingredient-option" data-ingredient="${esc(item.name)}" aria-label="Select ${esc(item.name)}"><span class="ingredient-option-image" aria-hidden="true">${item.emoji}</span><span class="ingredient-option-name">${esc(item.name)}</span><span class="ingredient-option-category">${esc(item.category)}</span></button>`).join('') : '<p class="ingredient-no-results">No matches. You can enter the ingredient manually below.</p>';
}
renderIngredientMenu();
$('#ingredientSearch')?.addEventListener('input', e => renderIngredientMenu(e.target.value));
$('#ingredientMenu')?.addEventListener('click', e => {
  const option = e.target.closest('[data-ingredient]');
  if (!option) return;
  const item = commonIngredients.find(entry => entry.name === option.dataset.ingredient);
  if (!item) return;
  $('#foodName').value = item.name;
  $('#foodCategory').value = item.category;
  $('#foodUnit').value = item.unit;
  $('#foodQuantity').value = 1;
  $('#ingredientMenu').querySelectorAll('.ingredient-option').forEach(button => button.classList.toggle('selected', button === option));
  $('#foodName').focus();
});
function openModal() {
  editingFoodId = null;
  $('#modalTitle').textContent = 'New ingredient';
  $('.modal-heading .eyebrow').textContent = 'ADD TO YOUR PANTRY';
  $('#saveFoodBtn').textContent = 'Save ingredient';
  $('#foodForm').reset();
  $('#ingredientPicker').hidden = false;
  $('#ingredientSearch').value = '';
  renderIngredientMenu();
  $('#purchaseDate').value = new Date().toISOString().slice(0,10);
  modal.classList.add('open');
  modal.setAttribute('aria-hidden','false');
  $('#foodName').focus();
}
function openEditModal(id) {
  const food = foods.find(item => String(item.id) === String(id));
  if (!food) return;
  editingFoodId = food.id;
  $('#ingredientPicker').hidden = true;
  $('#modalTitle').textContent = 'Edit ingredient';
  $('.modal-heading .eyebrow').textContent = 'UPDATE YOUR PANTRY';
  $('#saveFoodBtn').textContent = 'Save changes';
  $('#foodName').value = food.name || '';
  $('#foodQuantity').value = food.quantity;
  $('#foodUnit').value = food.unit || 'item';
  $('#foodCategory').value = food.category || 'Other';
  $('#purchaseDate').value = food.purchase_date || '';
  $('#expiryDate').value = food.expiry_date || '';
  $('#foodValue').value = food.estimated_value ?? 0;
  modal.classList.add('open');
  modal.setAttribute('aria-hidden','false');
  $('#foodName').focus();
}
function closeModal() {
  modal.classList.remove('open');
  modal.setAttribute('aria-hidden','true');
  $('#foodForm').reset();
  $('#ingredientPicker').hidden = false;
  $('#ingredientSearch').value = '';
  renderIngredientMenu();
  editingFoodId = null;
}
$('#openAddModal').addEventListener('click', openModal);
$('#closeModal').addEventListener('click', closeModal);
$('#cancelModal').addEventListener('click', closeModal);
modal.addEventListener('click', e => { if (e.target === modal) closeModal(); });
document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
$('#foodForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#saveFoodBtn');
  btn.disabled = true;
  btn.textContent = 'Saving…';
  const payload = {
    name: $('#foodName').value.trim(),
    quantity: Number($('#foodQuantity').value),
    unit: $('#foodUnit').value,
    category: $('#foodCategory').value,
    purchase_date: $('#purchaseDate').value || null,
    expiry_date: $('#expiryDate').value || null,
    estimated_value: Number($('#foodValue').value || 0)
  };
  try {
    if (editingFoodId !== null) {
      await api(`/api/foods/${editingFoodId}`, {method:'PUT',body:JSON.stringify(payload)});
      closeModal();
      await 

      toast('Ingredient updated.');
    } else {
      await api('/api/foods', {method:'POST',body:JSON.stringify(payload)});
      closeModal();
      await refreshAll();
      toast('Ingredient added to your pantry.');
    }
  } catch (err) { toast(err.message); }
  finally { btn.disabled = false; btn.textContent = editingFoodId !== null ? 'Save changes' : 'Save ingredient'; }
});
async function deleteFood(id) {
  const food = foods.find(item => String(item.id) === String(id));
  if (!food) return;
  const confirmed = await showConfirmDialog({title:'Remove ingredient?', message:'This ingredient will be removed from your pantry. Past activity records will remain in your impact statistics.', food, eyebrow:'PANTRY UPDATE', icon:'−', confirmLabel:'Remove ingredient', danger:true});
  if (!confirmed) return;
  try {
    await api(`/api/foods/${id}`, {method:'DELETE'});
    await refreshAll();
    toast('Ingredient removed from your pantry.');
  } catch (err) { toast(err.message); }
}
async function recordFoodEvent(id, eventType) {
  const food = foods.find(f => String(f.id) === String(id));
  if (!food) return;
  const isUsed = eventType === 'used';
  const confirmed = await showConfirmDialog({title:isUsed ? 'Mark as used?' : 'Record food waste?', message:isUsed ? 'This will update your ingredient quantity and your food-saving impact.' : 'This will record the ingredient as wasted and update your impact statistics.', food, eyebrow:isUsed ? 'NICE WORK' : 'WASTE TRACKING', icon:isUsed ? '✓' : '↗', confirmLabel:isUsed ? 'Yes, mark as used' : 'Record as wasted', danger:!isUsed});
  if (!confirmed) return;
  try {
    await api(`/api/foods/${id}/event`, {method:'POST',body:JSON.stringify({event_type:eventType,quantity:food.quantity})});
    await refreshAll();
    toast(eventType === 'used' ? 'Nice! Ingredient use recorded.' : 'Waste recorded. Honest tracking helps you improve.');
  } catch (err) { toast(err.message); }
}
$('#foodSearch').addEventListener('input', renderPantry);
$('#categoryFilter').addEventListener('change', renderPantry);
$('#sortFilter').addEventListener('change', renderPantry);
$('#daysSegments').addEventListener('click', e => {
  const btn = e.target.closest('[data-days]');
  if (!btn) return;
  selectedDays = Number(btn.dataset.days);
  $$('#daysSegments button').forEach(b => b.classList.toggle('selected', b === btn));
});
$('#mealPlanForm').addEventListener('submit', async e => {
  e.preventDefault();
  const btn = $('#generatePlanBtn');
  const output = $('#mealPlanOutput');
  btn.disabled = true;
  btn.textContent = '✦ Planning your meals…';
  output.innerHTML = '<div class="plan-placeholder"><div class="plan-plate">⏳</div><h3>Building your plan…</h3><p>Looking at your pantry, budget and preferences.</p></div>';
  try {
    const result = await api('/api/meal-plan',{method:'POST',body:JSON.stringify({
      budget_rm:Number($('#budgetInput').value),
      days:selectedDays,
      preferences:$('#preferencesInput').value.trim()
    })});
    renderMealPlan(result);
    toast(result.mode === 'gemini' ? 'AI meal plan generated.' : 'Demo meal plan generated. Add a Gemini key to enable live AI.');
  } catch (err) {
    output.innerHTML = `<div class="empty-state">${esc(err.message)}</div>`;
    toast(err.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = '✦ Generate my plan';
  }
});
function renderMealPlan(plan) {
  const days = Array.isArray(plan.days) ? plan.days : [];
  $('#mealPlanOutput').innerHTML = `
    <div class="plan-summary"><strong>${esc(plan.summary || 'Your budget-friendly meal plan')}</strong><p>Estimated extra spend: <b>RM ${money(plan.estimated_total_rm)}</b> · ${plan.mode === 'gemini' ? 'Gemini AI plan' : 'Local demo suggestions'}</p>${plan.fallback_reason ? `<p class="plan-notice">${esc(plan.fallback_reason)}</p>` : ''}</div>
    ${days.map(day => `<article class="meal-card"><div class="meal-card-head"><span class="day-tag">DAY ${esc(day.day)}</span><div style="flex:1;min-width:0"><h3>${esc(day.name || 'Meal idea')}</h3></div><span class="meal-cost">RM ${money(day.estimated_extra_cost_rm)}</span></div>
      <div class="ingredient-tags">${(day.ingredients_to_use || []).map(i=>`<span class="ingredient-tag">✓ ${esc(i)}</span>`).join('') || '<span class="ingredient-tag">Use pantry ingredients</span>'}</div>
      <p>${esc(day.instructions || '')}</p>
      ${(day.shopping_list || []).length ? `<p><b>Shopping list:</b> ${(day.shopping_list || []).map(i=>`${esc(i.item)} (RM ${money(i.estimated_cost_rm)})`).join(', ')}</p>` : ''}
      </article>`).join('')}
    <p class="plan-notice">${esc(plan.notice || 'Costs are estimates. Check ingredients, allergies and food safety before cooking.')}${plan.food_safety_note ? ' '+esc(plan.food_safety_note):''}</p>`;
}
// Profile editor
const profileBackdrop = $('#profileBackdrop');
const profileForm = $('#profileForm');
async function openProfileEditor() {
  try {
    const data = await api('/api/profile');
    const p = data.profile || {};
    ['name','email','age','gender','phone','dietary_preferences'].forEach(key => {
      const field = $('#profile-' + key);
      if (field) field.value = p[key] ?? '';
    });
    if (profileBackdrop) profileBackdrop.classList.add('open');
  } catch (error) { toast(error.message); }
}
const profileButton = $('#profileOpen');
if (profileButton) profileButton.addEventListener('click', openProfileEditor);
const profileClose = $('#profileClose');
const profileCancel = $('#profileCancel');
[profileClose, profileCancel].forEach(button => button && button.addEventListener('click', () => profileBackdrop?.classList.remove('open')));
if (profileBackdrop) profileBackdrop.addEventListener('click', e => { if (e.target === profileBackdrop) profileBackdrop.classList.remove('open'); });
if (profileForm) profileForm.addEventListener('submit', async e => {
  e.preventDefault();
  const payload = {};
  ['name','email','age','gender','phone','dietary_preferences'].forEach(key => {
    const field = $('#profile-' + key);
    payload[key] = field ? field.value.trim() : '';
  });
  try {
    const data = await api('/api/profile', {method:'PUT', body:JSON.stringify(payload)});
    const p = data.profile || payload;
    $$('.profile strong').forEach(el => el.textContent = p.name || 'Your kitchen');
    $$('.avatar').forEach(el => { if (el.classList.contains('small-avatar') || el.closest('.profile')) el.textContent = (p.name || 'U').slice(0,1).toUpperCase(); });
    profileBackdrop.classList.remove('open');
    toast(data.message || 'Profile updated.');
  } catch (error) { toast(error.message); }
});

refreshAll();

