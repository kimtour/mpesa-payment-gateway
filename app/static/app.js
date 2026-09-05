const form = document.querySelector('#payment-form');
const message = document.querySelector('#message');
const tableBody = document.querySelector('#transactions');
const statusFilter = document.querySelector('#status-filter');
const searchInput = document.querySelector('#search');

function money(value) {
  return new Intl.NumberFormat('en-KE', {style: 'currency', currency: 'KES'}).format(value);
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
}

function showMessage(text, error = false) {
  message.textContent = text;
  message.className = `message${error ? ' error' : ''}`;
}

async function request(url, options = {}) {
  const response = await fetch(url, options);
  const contentType = response.headers.get('content-type') || '';
  const body = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) throw new Error(body?.detail || `Request failed with status ${response.status}`);
  return body;
}

function actionButtons(payment) {
  const id = escapeHtml(payment.checkout_request_id);
  if (payment.status === 'PENDING') {
    return `<div class="action-group">
      <button class="small-button" data-id="${id}" data-action="complete">Complete</button>
      <button class="small-button cancel" data-id="${id}" data-action="cancel">Cancel</button>
    </div>`;
  }
  if (payment.status === 'COMPLETED') {
    return `<button class="small-button refund" data-id="${id}" data-action="refund">Refund</button>`;
  }
  return 'Done';
}

async function loadTransactions() {
  const params = new URLSearchParams({limit: '50'});
  if (statusFilter.value) params.set('status', statusFilter.value);
  if (searchInput.value.trim()) params.set('search', searchInput.value.trim());
  const payments = await request(`/api/payments?${params}`);
  tableBody.innerHTML = payments.length ? payments.map(payment => `
    <tr>
      <td>${escapeHtml(payment.account_reference)}</td>
      <td>${escapeHtml(payment.phone_number.replace(/(254)(\d{3})(\d{3})(\d{3})/, '+$1 $2 $3 $4'))}</td>
      <td>${money(payment.amount)}</td>
      <td><span class="status ${escapeHtml(payment.status)}">${escapeHtml(payment.status)}</span></td>
      <td>${escapeHtml(payment.mpesa_receipt_number || 'Pending')}</td>
      <td>${actionButtons(payment)}</td>
    </tr>`).join('') : '<tr><td colspan="6">No matching transactions.</td></tr>';
}

async function loadStats() {
  const stats = await request('/api/payments/stats');
  document.querySelector('#stat-total').textContent = stats.total_transactions;
  document.querySelector('#stat-value').textContent = money(stats.completed_value);
  document.querySelector('#stat-rate').textContent = `${stats.success_rate}%`;
  document.querySelector('#stat-pending').textContent = stats.pending;
}

async function loadDashboard() {
  try {
    await Promise.all([loadTransactions(), loadStats()]);
  } catch (error) {
    showMessage(error.message, true);
  }
}

async function runAction(checkoutId, action) {
  const encodedId = encodeURIComponent(checkoutId);
  let url = `/api/payments/${encodedId}/${action}`;
  const options = {method: 'POST'};
  if (action === 'complete') {
    url = '/api/payments/demo-callback';
    options.headers = {'Content-Type': 'application/json', 'X-Callback-Token': 'demo-callback-token'};
    options.body = JSON.stringify({checkout_request_id: checkoutId, successful: true});
  }
  try {
    await request(url, options);
    showMessage(`Payment ${action} action completed successfully.`);
    await loadDashboard();
  } catch (error) {
    showMessage(error.message, true);
  }
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const idempotencyKey = crypto.randomUUID ? crypto.randomUUID() : `demo-${Date.now()}`;
  try {
    const result = await request('/api/payments/stk-push', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Idempotency-Key': idempotencyKey},
      body: JSON.stringify({
        phone_number: document.querySelector('#phone').value,
        amount: Number(document.querySelector('#amount').value),
        account_reference: document.querySelector('#reference').value,
        description: 'Payment gateway demonstration'
      })
    });
    showMessage(`STK Push accepted. ID: ${result.checkout_request_id}`);
    await loadDashboard();
  } catch (error) {
    showMessage(error.message, true);
  }
});

tableBody.addEventListener('click', event => {
  const button = event.target.closest('button[data-action]');
  if (button) runAction(button.dataset.id, button.dataset.action);
});

document.querySelector('#refresh').addEventListener('click', loadDashboard);
statusFilter.addEventListener('change', loadTransactions);
searchInput.addEventListener('input', () => {
  clearTimeout(searchInput.searchTimer);
  searchInput.searchTimer = setTimeout(loadTransactions, 250);
});

request('/api/health').then(() => {
  const health = document.querySelector('#health');
  health.textContent = 'API healthy';
  health.classList.add('ok');
}).catch(() => document.querySelector('#health').textContent = 'API unavailable');

loadDashboard();
