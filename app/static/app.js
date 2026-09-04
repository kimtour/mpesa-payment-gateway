const form = document.querySelector('#payment-form');
const message = document.querySelector('#message');
const tableBody = document.querySelector('#transactions');

function money(value) {
  return new Intl.NumberFormat('en-KE', {style: 'currency', currency: 'KES'}).format(value);
}

function showMessage(text, error = false) {
  message.textContent = text;
  message.className = `message${error ? ' error' : ''}`;
}

async function loadTransactions() {
  const response = await fetch('/api/payments');
  const payments = await response.json();
  tableBody.innerHTML = payments.length ? payments.map(payment => `
    <tr>
      <td>${payment.account_reference}</td>
      <td>${payment.phone_number.replace(/(254)(\d{3})(\d{3})(\d{3})/, '+$1 $2 $3 $4')}</td>
      <td>${money(payment.amount)}</td>
      <td><span class="status ${payment.status}">${payment.status}</span></td>
      <td>${payment.mpesa_receipt_number || 'Pending'}</td>
      <td>${payment.status === 'PENDING' ? `<button class="small-button" onclick="completePayment('${payment.checkout_request_id}')">Complete</button>` : 'Done'}</td>
    </tr>`).join('') : '<tr><td colspan="6">No transactions yet.</td></tr>';
}

async function completePayment(checkoutId) {
  const response = await fetch('/api/payments/demo-callback', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-Callback-Token': 'demo-callback-token'},
    body: JSON.stringify({checkout_request_id: checkoutId, successful: true})
  });
  showMessage(response.ok ? 'M-Pesa callback processed successfully.' : 'Callback failed.', !response.ok);
  await loadTransactions();
}

form.addEventListener('submit', async event => {
  event.preventDefault();
  const response = await fetch('/api/payments/stk-push', {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify({
      phone_number: document.querySelector('#phone').value,
      amount: Number(document.querySelector('#amount').value),
      account_reference: document.querySelector('#reference').value,
      description: 'Interview payment demo'
    })
  });
  const result = await response.json();
  showMessage(response.ok ? `STK Push accepted. ID: ${result.checkout_request_id}` : (result.detail?.[0]?.msg || result.detail), !response.ok);
  if (response.ok) await loadTransactions();
});

document.querySelector('#refresh').addEventListener('click', loadTransactions);

fetch('/api/health').then(r => r.json()).then(() => {
  const health = document.querySelector('#health');
  health.textContent = 'API healthy';
  health.classList.add('ok');
}).catch(() => document.querySelector('#health').textContent = 'API unavailable');

loadTransactions();
