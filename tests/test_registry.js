const assert = require('node:assert/strict');
const {selectDocuments, amountValue, dateValue} = require('../frontend/static/registry-utils.js');
const docs = [
    {id: 1, filename: 'Договор 10.pdf', folder_id: 'a', uploaded_at: '2026-09-18T10:00:00', extracted_data: {customer: 'ООО Берёза', contract_number: '01/26', amount: '9 007 199 254 740 993,01', currency: 'RUB', contract_date: '01.09.2026'}},
    {id: 2, filename: 'Договор 2.pdf', folder_id: null, uploaded_at: '2026-09-19T10:00:00', extracted_data: {customer: 'ООО Вектор', amount: '9 007 199 254 740 993,02', currency: 'RUB', contract_date: '18.08.2026'}},
    {id: 3, filename: 'Акт.pdf', folder_id: 'a', uploaded_at: '2026-09-17T10:00:00', extracted_data: {amount: 'Не найдено', currency: 'RUB'}},
];
const ids = options => selectDocuments(docs, options).map(doc => doc.id);
assert.deepEqual(ids({query: 'береза 01/26'}), [1]);
assert.deepEqual(ids({folder: 'a'}), [1, 3]);
assert.deepEqual(ids({folder: 'unfiled'}), [2]);
assert.deepEqual(ids({folder: 'a', query: 'Вектор'}), []);
assert.deepEqual(ids({sort: 'name_asc'}), [3, 2, 1]);
assert.deepEqual(ids({sort: 'amount_asc'}), [1, 2, 3]);
assert.deepEqual(ids({sort: 'amount_desc'}), [2, 1, 3]);
assert.deepEqual(ids({sort: 'date_desc'}), [1, 2, 3]);
assert.deepEqual(ids({sort: 'uploaded_asc'}), [3, 1, 2]);
assert.equal(amountValue('0,00'), 0n);
assert.equal(amountValue('от 100 до 200'), null);
assert.equal(amountValue(1250000.5), 125000050n);
assert.equal(amountValue(0), 0n);
assert.equal(amountValue(null), null);
assert.equal(amountValue('9007199254740993.01'), 900719925474099301n);
assert.equal(dateValue('2026-09-20'), '2026-09-20');
assert.equal(dateValue('20.09.2026'), '2026-09-20');
const canonical = [
    {id: 1, filename: 'Первый.pdf', extracted_data: {amount: 9007199254740994, currency: 'RUB', contract_date: '2026-09-20'}, display_data: {amount: '9 007 199 254 740 993,01', contract_date: '20.09.2026'}},
    {id: 2, filename: 'Второй.pdf', extracted_data: {amount: 9007199254740994, currency: 'RUB', contract_date: '2026-09-19'}, display_data: {amount: '9 007 199 254 740 993,02', contract_date: '19.09.2026'}},
];
assert.deepEqual(selectDocuments(canonical, {sort: 'amount_asc'}).map(d => d.id), [1, 2]);
assert.deepEqual(selectDocuments(canonical, {sort: 'date_asc'}).map(d => d.id), [2, 1]);
assert.deepEqual(selectDocuments(canonical, {query: '20.09.2026'}).map(d => d.id), [1]);
assert.deepEqual(selectDocuments(canonical, {query: '2026-09-20'}).map(d => d.id), [1]);
assert.deepEqual(docs.map(doc => doc.id), [1, 2, 3], 'Sorting does not mutate source');
console.log('Registry search, folder filters, dates, numeric sorting and precision: OK');
