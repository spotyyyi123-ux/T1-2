/* Pure registry filtering/sorting logic; also exercised by Node regression tests. */
(function (root) {
    const collator = new Intl.Collator('ru', { numeric: true, sensitivity: 'base' });
    const normalize = value => String(value ?? '').toLocaleLowerCase('ru').replace(/ё/g, 'е').replace(/\s+/g, ' ').trim();
    const missing = value => value == null || value === '' || value === 'Не найдено';

    function dateValue(value) {
        if (/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return value;
        const parts = /^(\d{2})\.(\d{2})\.(\d{4})$/.exec(value || '');
        return parts ? `${parts[3]}-${parts[2]}-${parts[1]}` : null;
    }

    function amountValue(value) {
        const text = String(value ?? '').replace(/\s/g, '');
        const parts = /^([+-]?)(\d+)(?:[.,](\d{1,2}))?$/.exec(text);
        if (!parts) return null;
        return BigInt(`${parts[1]}${parts[2]}${(parts[3] || '').padEnd(2, '0')}`);
    }

    function compareOptional(a, b, direction, comparator) {
        if (a == null && b == null) return 0;
        if (a == null) return 1;
        if (b == null) return -1;
        return direction * comparator(a, b);
    }

    function selectDocuments(documents, { folder = 'all', query = '', sort = 'uploaded_desc' } = {}) {
        const tokens = normalize(query).split(' ').filter(Boolean);
        const filtered = documents.filter(doc => {
            if (folder === 'unfiled' && doc.folder_id) return false;
            if (folder !== 'all' && folder !== 'unfiled' && doc.folder_id !== folder) return false;
            const fields = doc.extracted_data || {};
            const values = Object.values(fields).filter(value => typeof value === 'string' || typeof value === 'number');
            const haystack = normalize([doc.filename, ...values, ...Object.values(doc.display_data || {}),
                ...Object.values(fields.unparsed_values || {})].join(' '));
            return tokens.every(token => haystack.includes(token));
        });
        const direction = sort.endsWith('_desc') ? -1 : 1;
        filtered.sort((a, b) => {
            let comparison = 0;
            if (sort.startsWith('name_')) comparison = direction * collator.compare(a.filename, b.filename);
            else if (sort.startsWith('date_')) comparison = compareOptional(
                dateValue(a.extracted_data?.contract_date), dateValue(b.extracted_data?.contract_date), direction, collator.compare
            );
            else if (sort.startsWith('amount_')) {
                // Exact server-rendered amounts avoid JS Number precision loss for large sums.
                const av = amountValue(a.display_data?.amount ?? a.extracted_data?.amount);
                const bv = amountValue(b.display_data?.amount ?? b.extracted_data?.amount);
                // Different currencies are grouped, never implicitly converted or compared as equivalent.
                const ac = missing(a.extracted_data?.currency) ? null : a.extracted_data.currency;
                const bc = missing(b.extracted_data?.currency) ? null : b.extracted_data.currency;
                comparison = compareOptional(ac, bc, 1, collator.compare)
                    || compareOptional(av, bv, direction, (x, y) => x < y ? -1 : x > y ? 1 : 0);
            } else if (sort === 'status_asc') comparison = collator.compare(a.status, b.status);
            else comparison = compareOptional(a.uploaded_at || null, b.uploaded_at || null, direction, collator.compare);
            return comparison || Number(b.id) - Number(a.id);
        });
        return filtered;
    }

    const api = { selectDocuments, amountValue, dateValue };
    if (typeof module !== 'undefined' && module.exports) module.exports = api;
    else root.Registry = api;
})(typeof window !== 'undefined' ? window : this);
