// Library controls share the authenticated session and detail dialog in frontend/index.html.
let libraryFolders = [];
let currentFolder = 'all';
let libraryRequest = 0;
let mutationBusy = false;
let draggedDocumentId = null;
let folderRenderSignature = null;
let pendingAction = null;
const actionDialog = document.getElementById('actionDialog');
const searchInput = document.getElementById('documentSearch');
const sortInput = document.getElementById('documentSort');

function uploadFolderId() {
    return libraryFolders.some(folder => folder.id === currentFolder) ? currentFolder : null;
}

function folderName(id) {
    return libraryFolders.find(folder => folder.id === id)?.name || 'Без папки';
}

async function libraryRequestJson(path, options = {}, session = accessToken) {
    const response = await fetch(`${API_BASE}${path}`, {
        ...options, headers: {'Authorization': `Bearer ${session}`, ...options.headers}
    });
    if (accessToken !== session) throw new Error('Сессия изменилась. Повторите действие.');
    if (response.status === 401) {
        logout();
        throw new Error('Сессия завершена. Войдите снова.');
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
        const detail = body?.detail;
        throw new Error(typeof detail === 'string' ? detail : `Не удалось выполнить запрос (${response.status}).`);
    }
    if (accessToken !== session) throw new Error('Сессия изменилась. Повторите действие.');
    return body;
}

async function loadLibrary(force = false) {
    if (!accessToken || mutationBusy || draggedDocumentId || (!force && loadingSession === accessToken)) return;
    const session = accessToken;
    const request = ++libraryRequest;
    loadingSession = session;
    try {
        const [documents, folders] = await Promise.all([
            libraryRequestJson('/documents', {}, session), libraryRequestJson('/folders', {}, session)
        ]);
        if (accessToken !== session || request !== libraryRequest || draggedDocumentId) return;
        const previousActive = documentsById.get(activeDocumentId);
        documentsById = new Map(documents.map(doc => [String(doc.id), doc]));
        libraryFolders = folders;
        if (currentFolder !== 'all' && currentFolder !== 'unfiled' && !folders.some(folder => folder.id === currentFolder)) currentFolder = 'unfiled';
        const currentActive = documentsById.get(activeDocumentId);
        if (documentDialog.open && !currentActive) documentDialog.close();
        else if (documentDialog.open && JSON.stringify(currentActive) !== JSON.stringify(previousActive)) {
            const scrollPosition = documentDialog.scrollTop;
            openDocumentDetails(activeDocumentId);
            documentDialog.scrollTop = scrollPosition;
        }
        document.getElementById('libraryError').classList.add('d-none');
        renderLibrary();
    } catch (error) {
        if (accessToken === session && request === libraryRequest) {
            const message = document.getElementById('libraryError');
            message.textContent = `Не удалось обновить реестр: ${error.message}`;
            message.classList.remove('d-none');
        }
    } finally {
        if (request === libraryRequest) loadingSession = null;
    }
}

function renderLibrary() {
    const documents = Array.from(documentsById.values());
    const counts = new Map();
    documents.forEach(doc => {
        const key = doc.folder_id || 'unfiled';
        counts.set(key, (counts.get(key) || 0) + 1);
    });
    const entries = [
        {id: 'all', name: 'Все документы', count: documents.length, icon: 'bi-files'},
        {id: 'unfiled', name: 'Без папки', count: counts.get('unfiled') || 0, icon: 'bi-inbox'},
        ...[...libraryFolders].sort((a, b) => a.name.localeCompare(b.name, 'ru')).map(folder => ({
            ...folder, count: counts.get(folder.id) || 0, icon: 'bi-folder'
        }))
    ];
    const folderSignature = JSON.stringify([entries, currentFolder]);
    if (folderSignature !== folderRenderSignature) {
        folderRenderSignature = folderSignature;
        const nav = document.getElementById('folderList');
        nav.replaceChildren();
        entries.forEach(entry => {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'folder-button';
            button.dataset.folderId = entry.id;
            button.title = entry.name;
            if (entry.id === currentFolder) button.setAttribute('aria-current', 'page');
            const icon = document.createElement('i');
            icon.className = `bi ${entry.icon}`;
            icon.setAttribute('aria-hidden', 'true');
            const name = document.createElement('span');
            name.className = 'folder-name';
            name.textContent = entry.name;
            const count = document.createElement('span');
            count.className = 'folder-count';
            count.textContent = entry.count;
            button.append(icon, name, count);
            nav.appendChild(button);
        });
    }
    const selected = entries.find(entry => entry.id === currentFolder);
    document.getElementById('currentFolderTitle').textContent = selected?.name || 'Все документы';
    document.getElementById('folderActions').classList.toggle('d-none', !uploadFolderId());
    document.getElementById('uploadDestination').textContent = `Новые документы попадут в «${folderName(uploadFolderId())}».`;
    const options = {folder: currentFolder, query: searchInput.value, sort: sortInput.value};
    const visible = Registry.selectDocuments(documents, options);
    document.getElementById('documentCount').textContent = `Показано ${visible.length} из ${selected?.count || 0}`;
    document.getElementById('sortNote').classList.toggle('d-none', !sortInput.value.startsWith('amount_'));
    const signature = JSON.stringify([visible, options]);
    if (signature !== renderedRegistry && !draggedDocumentId) {
        renderedRegistry = signature;
        renderDocumentRows(visible);
    }
}

function resetLibrary() {
    libraryRequest++;
    loadingSession = null;
    mutationBusy = false;
    draggedDocumentId = null;
    libraryFolders = [];
    currentFolder = 'all';
    folderRenderSignature = null;
    pendingAction = null;
    if (actionDialog.open) actionDialog.close();
    searchInput.value = '';
    sortInput.value = 'uploaded_desc';
    document.getElementById('folderList').replaceChildren();
    document.getElementById('libraryError').classList.add('d-none');
}

function openLibraryAction(kind, id = null) {
    if (mutationBusy) return;
    const doc = documentsById.get(String(id));
    if ((kind === 'move' || kind === 'deleteDocument') && !doc) return;
    pendingAction = {kind, id: id ?? currentFolder};
    const nameGroup = document.getElementById('folderNameGroup');
    const nameInput = document.getElementById('folderNameInput');
    const moving = kind === 'move';
    const naming = kind === 'create' || kind === 'rename';
    const deleting = kind === 'deleteFolder' || kind === 'deleteDocument';
    nameGroup.hidden = !naming;
    nameInput.disabled = !naming;
    nameInput.required = naming;
    nameInput.value = kind === 'rename' ? folderName(currentFolder) : '';
    document.getElementById('moveFolderGroup').hidden = !moving;
    document.getElementById('actionError').hidden = true;
    const submit = document.getElementById('confirmActionBtn');
    submit.disabled = false;
    document.getElementById('cancelActionBtn').disabled = false;
    submit.className = deleting ? 'btn btn-danger' : 'btn btn-primary';
    submit.textContent = deleting ? 'Удалить' : moving ? 'Переместить' : naming && kind === 'create' ? 'Создать' : 'Сохранить';
    document.getElementById('actionTitle').textContent = {
        create: 'Новая папка', rename: 'Переименовать папку', move: 'Переместить документ',
        deleteFolder: 'Удалить папку?', deleteDocument: 'Удалить документ?'
    }[kind];
    document.getElementById('actionDescription').textContent = {
        create: 'Соберите связанные документы в одной папке.',
        rename: 'Новое название будет сохранено для этой папки.',
        move: doc?.filename || '',
        deleteFolder: `Папка «${folderName(currentFolder)}» будет удалена. Её документы останутся в разделе «Без папки».`,
        deleteDocument: `«${doc?.filename}»: файл, результат анализа и история обработки будут удалены без возможности восстановления.`
    }[kind];
    if (moving) {
        const select = document.getElementById('moveFolderSelect');
        select.replaceChildren();
        [{id: '', name: 'Без папки'}, ...libraryFolders].forEach(folder => {
            const option = document.createElement('option');
            option.value = folder.id;
            option.textContent = folder.name;
            select.appendChild(option);
        });
        select.value = doc.folder_id || '';
    }
    actionDialog.showModal();
    if (naming) nameInput.focus();
    else if (moving) document.getElementById('moveFolderSelect').focus();
    else document.getElementById('cancelActionBtn').focus();
}

async function mutateLibrary(action) {
    if (mutationBusy) return;
    const session = accessToken;
    mutationBusy = true;
    libraryRequest++; // Discard any polling response that predates this change.
    loadingSession = null;
    try {
        return await action();
    } finally {
        if (accessToken === session) {
            mutationBusy = false;
            await loadLibrary(true);
        }
    }
}

function jsonOptions(method, body) {
    return {method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)};
}

document.getElementById('actionForm').addEventListener('submit', async event => {
    event.preventDefault();
    if (!pendingAction || mutationBusy) return;
    const action = {...pendingAction};
    const submit = document.getElementById('confirmActionBtn');
    const cancel = document.getElementById('cancelActionBtn');
    submit.disabled = cancel.disabled = true;
    document.getElementById('actionError').hidden = true;
    try {
        let message;
        await mutateLibrary(async () => {
            if (action.kind === 'create') {
                const folder = await libraryRequestJson('/folders', jsonOptions('POST', {name: document.getElementById('folderNameInput').value.trim()}));
                currentFolder = folder.id;
                message = 'Папка создана';
            } else if (action.kind === 'rename') {
                await libraryRequestJson(`/folders/${action.id}`, jsonOptions('PATCH', {name: document.getElementById('folderNameInput').value.trim()}));
                message = 'Папка переименована';
            } else if (action.kind === 'deleteFolder') {
                await libraryRequestJson(`/folders/${action.id}`, {method: 'DELETE'});
                currentFolder = 'unfiled';
                message = 'Папка удалена. Документы остались в «Без папки».';
            } else if (action.kind === 'move') {
                await libraryRequestJson(`/documents/${action.id}/folder`, jsonOptions('PATCH', {folder_id: document.getElementById('moveFolderSelect').value || null}));
                message = 'Документ перемещён';
            } else if (action.kind === 'deleteDocument') {
                const result = await libraryRequestJson(`/documents/${action.id}`, {method: 'DELETE'});
                message = result.cleanup_pending ? 'Документ удалён из реестра, но очистка хранилища требует внимания администратора.' : 'Документ и его файл удалены';
            }
        });
        actionDialog.close();
        showAlert(message, 'success');
    } catch (error) {
        const errorElement = document.getElementById('actionError');
        errorElement.textContent = error.message;
        errorElement.hidden = false;
    } finally {
        submit.disabled = cancel.disabled = false;
    }
});

document.getElementById('createFolderBtn').addEventListener('click', () => openLibraryAction('create'));
document.getElementById('renameFolderBtn').addEventListener('click', () => openLibraryAction('rename'));
document.getElementById('deleteFolderBtn').addEventListener('click', () => openLibraryAction('deleteFolder'));
document.getElementById('cancelActionBtn').addEventListener('click', () => actionDialog.close());
actionDialog.addEventListener('cancel', event => { if (mutationBusy) event.preventDefault(); });
actionDialog.addEventListener('close', () => { pendingAction = null; });
searchInput.addEventListener('input', renderLibrary);
sortInput.addEventListener('change', renderLibrary);
document.getElementById('clearSearchBtn').addEventListener('click', () => { searchInput.value = ''; renderLibrary(); searchInput.focus(); });
document.getElementById('folderList').addEventListener('click', event => {
    const target = event.target.closest('button[data-folder-id]');
    if (!target) return;
    currentFolder = target.dataset.folderId;
    renderLibrary();
});

const DOCUMENT_DRAG_TYPE = 'application/x-contract-document';
document.getElementById('tableBody').addEventListener('dragstart', event => {
    const row = event.target.closest('tr[data-document-id]');
    if (!row || mutationBusy || event.target.closest('button')) { event.preventDefault(); return; }
    draggedDocumentId = row.dataset.documentId;
    row.classList.add('dragging');
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData(DOCUMENT_DRAG_TYPE, draggedDocumentId);
});
document.addEventListener('dragend', () => {
    draggedDocumentId = null;
    document.querySelectorAll('.dragging, .drop-target').forEach(node => node.classList.remove('dragging', 'drop-target'));
});
const folderList = document.getElementById('folderList');
folderList.addEventListener('dragover', event => {
    const target = event.target.closest('button[data-folder-id]');
    if (!draggedDocumentId || !target || target.dataset.folderId === 'all') return;
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
    document.querySelectorAll('.drop-target').forEach(node => node.classList.remove('drop-target'));
    target.classList.add('drop-target');
});
folderList.addEventListener('dragleave', event => {
    const target = event.target.closest('button[data-folder-id]');
    if (target && !target.contains(event.relatedTarget)) target.classList.remove('drop-target');
});
folderList.addEventListener('drop', async event => {
    const target = event.target.closest('button[data-folder-id]');
    if (!target || target.dataset.folderId === 'all' || !draggedDocumentId) return;
    event.preventDefault();
    const id = event.dataTransfer.getData(DOCUMENT_DRAG_TYPE);
    const destination = target.dataset.folderId === 'unfiled' ? null : target.dataset.folderId;
    draggedDocumentId = null;
    target.classList.remove('drop-target');
    if (!documentsById.has(id) || mutationBusy || (documentsById.get(id).folder_id || null) === destination) return;
    try {
        await mutateLibrary(() => libraryRequestJson(`/documents/${id}/folder`, jsonOptions('PATCH', {folder_id: destination})));
        showAlert(`Документ перемещён в «${folderName(destination)}»`, 'success');
    } catch (error) { showAlert(error.message); }
});
