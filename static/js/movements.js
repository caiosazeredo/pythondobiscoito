// Variáveis globais para armazenar os métodos de pagamento
let paymentMethodsData = {};

document.addEventListener('DOMContentLoaded', function () {
    // Inicializar funcionalidades principais
    initializeDateFilter();
    initializePaymentMethods();
    initializeExpenseCategories();
    initializeSingleMovementForm(); 

    // Inicializar registro em lote apenas se não for caixa financeiro
    const batchTab = document.getElementById('batch-tab');
    if (batchTab) {
        initializeBatchMovements();
    }
});

// Função para inicializar o filtro de data
function initializeDateFilter() {
    const dateFilter = document.getElementById('dateFilter');
    const formDate = document.getElementById('formDate');

    if (!dateFilter) return;

    // 1. mudar a data só recarrega a página
    dateFilter.addEventListener('change', () => {
        const newDate = dateFilter.value;
        // mantém ?date=AAAA-MM-DD na URL
        const url = new URL(window.location.href);
        url.searchParams.set('date', newDate);
        window.location.href = url.toString();
    });

    // 2. garante que o hidden acompanha o seletor
    if (formDate) {
        dateFilter.addEventListener('change', () => formDate.value = dateFilter.value);
    }
}

// Função para inicializar os métodos de pagamento
function initializePaymentMethods() {
    const paymentMethodMain = document.getElementById('payment_method_main');
    const paymentMethodDetail = document.getElementById('payment_method');

    if (!paymentMethodMain || !paymentMethodDetail) return;

    // Função para carregar formas de pagamento detalhadas
    function loadPaymentMethods(parentId) {
        fetch(`/api/payment_methods/${parentId}`)
            .then(response => response.json())
            .then(data => {
                paymentMethodDetail.innerHTML = '';

                if (data.length === 0) {
                    // Se não houver subcategorias, usa o próprio método principal
                    const option = document.createElement('option');
                    option.value = parentId;
                    option.textContent = paymentMethodMain.options[paymentMethodMain.selectedIndex].textContent;
                    option.setAttribute('data-category', paymentMethodMain.options[paymentMethodMain.selectedIndex].getAttribute('data-category'));
                    paymentMethodDetail.appendChild(option);
                } else {
                    // Adiciona opção padrão
                    const defaultOption = document.createElement('option');
                    defaultOption.value = '';
                    defaultOption.textContent = 'Selecione';
                    paymentMethodDetail.appendChild(defaultOption);

                    // Adiciona subcategorias
                    data.forEach(method => {
                        const option = document.createElement('option');
                        option.value = method.id;
                        option.textContent = method.name;
                        option.setAttribute('data-category', method.category);
                        paymentMethodDetail.appendChild(option);
                    });
                }

                // Armazenar dados para uso posterior
                paymentMethodsData[parentId] = data;
            })
            .catch(error => console.error('Erro ao carregar formas de pagamento:', error));
    }

    paymentMethodMain.addEventListener('change', function () {
        if (this.value) {
            loadPaymentMethods(this.value);
        } else {
            paymentMethodDetail.innerHTML = '<option value="">Selecione o tipo de pagamento primeiro</option>';
        }
    });
}

// Função para inicializar categorias de despesa
function initializeExpenseCategories() {
    const expenseCategoryContainer = document.getElementById('expenseCategoryContainer');
    const typeRadios = document.getElementsByName('type');

    if (!expenseCategoryContainer || typeRadios.length === 0) return;

    for (const radio of typeRadios) {
        radio.addEventListener('change', function () {
            if (this.value === 'saida') {
                expenseCategoryContainer.style.display = 'none';
            } else if (this.value === 'despesa_loja') {
                expenseCategoryContainer.style.display = 'block';
            }
        });
    }

    // Disparar evento para configuração inicial
    const checkedRadio = document.querySelector('input[name="type"]:checked');
    if (checkedRadio) {
        checkedRadio.dispatchEvent(new Event('change'));
    }
}

// Função para inicializar movimentações em lote
function initializeBatchMovements() {
    const batchForm = document.getElementById('batchMovementsForm');
    const batchContainer = document.getElementById('batchEntriesContainer');
    const addEntryBtn = document.getElementById('addBatchEntry');
    const saveAllBtn = document.getElementById('saveBatchEntries');

    if (!batchForm || !batchContainer || !addEntryBtn || !saveAllBtn) {
        return;
    }

    let entryIdCounter = 0;
    let lastPaymentMethod = null;
    let lastPaymentDetail = null;
    let isProcessing = false; // Controle para evitar duplo processamento

    // Função para carregar opções detalhadas de pagamento para lote
    function loadBatchPaymentDetails(parentId, selectElement) {
        return new Promise((resolve, reject) => {
            // Verificar se já temos os dados em cache
            if (paymentMethodsData[parentId]) {
                updateSelectOptions(selectElement, paymentMethodsData[parentId], parentId);
                resolve();
            } else {
                fetch(`/api/payment_methods/${parentId}`)
                    .then(response => response.json())
                    .then(data => {
                        paymentMethodsData[parentId] = data;
                        updateSelectOptions(selectElement, data, parentId);
                        resolve();
                    })
                    .catch(error => {
                        console.error('Erro ao carregar formas de pagamento:', error);
                        reject(error);
                    });
            }
        });
    }

    // Função para atualizar as opções do select
    function updateSelectOptions(selectElement, data, parentId) {
        selectElement.innerHTML = '';

        if (data.length === 0) {
            const option = document.createElement('option');
            option.value = parentId;
            const mainSelect = selectElement.closest('.batch-entry').querySelector('.batch-payment-method');
            option.textContent = mainSelect.options[mainSelect.selectedIndex].textContent;
            selectElement.appendChild(option);

            if (lastPaymentMethod === parentId) {
                lastPaymentDetail = parentId;
                option.selected = true;
            }
        } else {
            // Adiciona opção padrão
            const defaultOption = document.createElement('option');
            defaultOption.value = '';
            defaultOption.textContent = 'Selecione';
            selectElement.appendChild(defaultOption);

            // Adiciona subcategorias
            let foundLastDetail = false;
            data.forEach(method => {
                const option = document.createElement('option');
                option.value = method.id;
                option.textContent = method.name;

                if (lastPaymentDetail && method.id.toString() === lastPaymentDetail.toString()) {
                    option.selected = true;
                    foundLastDetail = true;
                }

                selectElement.appendChild(option);
            });

            // Se não encontrou o último detalhamento, selecionar o primeiro
            if (!foundLastDetail && data.length > 0 && selectElement.options.length > 1) {
                selectElement.options[1].selected = true;
                lastPaymentDetail = selectElement.options[1].value;
            }
        }
    }

    // Função para adicionar uma nova linha de entrada
    function addBatchEntry() {
        entryIdCounter++;

        const entryRow = document.createElement('div');
        entryRow.className = 'batch-entry row mb-2 border-bottom pb-2';
        entryRow.setAttribute('data-entry-id', entryIdCounter);
        entryRow.setAttribute('data-entry-active', 'true'); // NOVO: marcar como ativo

        let paymentMethodOptions = '<option value="">Selecione</option>';

        // Copiar opções do select principal
        const mainSelectOptions = document.querySelectorAll('#payment_method_main option');
        mainSelectOptions.forEach(option => {
            if (option.value) {
                if (lastPaymentMethod && option.value === lastPaymentMethod) {
                    paymentMethodOptions += `<option value="${option.value}" data-category="${option.getAttribute('data-category')}" selected>${option.textContent}</option>`;
                } else {
                    paymentMethodOptions += `<option value="${option.value}" data-category="${option.getAttribute('data-category')}">${option.textContent}</option>`;
                }
            }
        });

        entryRow.innerHTML = `
            <div class="col-md-3">
                <select class="form-select batch-payment-method" name="batch_payment_method_${entryIdCounter}" required>
                    ${paymentMethodOptions}
                </select>
            </div>
            <div class="col-md-3">
                <select class="form-select batch-payment-detail" name="batch_payment_detail_${entryIdCounter}" required>
                    <option value="">Selecione o tipo primeiro</option>
                </select>
            </div>
            <div class="col-md-2">
                <div class="input-group">
                    <span class="input-group-text">R$</span>
                    <input type="number" class="form-control batch-amount" name="batch_amount_${entryIdCounter}" step="0.01" min="0.01" required>
                </div>
            </div>
            <div class="col-md-3">
                <input type="text" class="form-control batch-description" name="batch_description_${entryIdCounter}" placeholder="Descrição (opcional)">
            </div>
            <div class="col-md-1">
                <button type="button" class="btn btn-danger btn-sm remove-entry">
                    <i class="bi bi-trash"></i>
                </button>
            </div>
        `;

        batchContainer.appendChild(entryRow);

        // Adicionar event listeners
        const paymentMethodSelect = entryRow.querySelector('.batch-payment-method');
        const paymentDetailSelect = entryRow.querySelector('.batch-payment-detail');
        const removeBtn = entryRow.querySelector('.remove-entry');
        const amountInput = entryRow.querySelector('.batch-amount');

        // Carregar opções detalhadas com base no método de pagamento
        paymentMethodSelect.addEventListener('change', async function () {
            if (this.value) {
                lastPaymentMethod = this.value;
                await loadBatchPaymentDetails(this.value, paymentDetailSelect);
            } else {
                paymentDetailSelect.innerHTML = '<option value="">Selecione o tipo primeiro</option>';
                lastPaymentDetail = null;
            }
        });

        // Salvar último detalhamento selecionado
        paymentDetailSelect.addEventListener('change', function () {
            if (this.value) {
                lastPaymentDetail = this.value;
            }
        });

        // Se tiver valor inicial, disparar o change
        if (paymentMethodSelect.value) {
            paymentMethodSelect.dispatchEvent(new Event('change'));
        }

        // Remover entrada
        removeBtn.addEventListener('click', function () {
            // NOVO: marcar como inativo antes de remover do DOM
            entryRow.setAttribute('data-entry-active', 'false');
            
            // Adicionar classe para feedback visual
            entryRow.classList.add('removing');
            entryRow.style.opacity = '0.5';
            
            // Aguardar um momento e então remover
            setTimeout(() => {
                if (entryRow && entryRow.parentNode) {
                    entryRow.remove();
                }
            }, 100);
        });

        // Permitir adicionar nova linha ao pressionar Enter
        amountInput.addEventListener('keypress', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                if (this.value && parseFloat(this.value) > 0) {
                    addBatchEntry();
                    // Focar no próximo select de forma de pagamento
                    setTimeout(() => {
                        const lastEntry = batchContainer.querySelector('.batch-entry:last-child');
                        if (lastEntry) {
                            const firstSelect = lastEntry.querySelector('.batch-payment-method');
                            if (firstSelect) firstSelect.focus();
                        }
                    }, 100);
                }
            }
        });
    }

    // Adicionar primeira entrada ao clicar no botão
    addEntryBtn.addEventListener('click', function () {
        if (isProcessing) return; // NOVO: prevenir adição durante processamento
        
        addBatchEntry();
        // Focar no primeiro campo da nova entrada
        setTimeout(() => {
            const lastEntry = batchContainer.querySelector('.batch-entry:last-child');
            if (lastEntry) {
                const firstSelect = lastEntry.querySelector('.batch-payment-method');
                if (firstSelect) firstSelect.focus();
            }
        }, 100);
    });

    // Salvar todas as entradas - VERSÃO COMPLETAMENTE CORRIGIDA
    saveAllBtn.addEventListener('click', async function () {
        // Evitar duplo processamento
        if (isProcessing) {
            return;
        }
        isProcessing = true;

        // NOVO: Desabilitar todos os botões e adicionar feedback visual
        addEntryBtn.disabled = true;
        saveAllBtn.disabled = true;
        
        // Desabilitar botões de remoção
        const removeButtons = batchContainer.querySelectorAll('.remove-entry');
        removeButtons.forEach(btn => btn.disabled = true);
        
        // Atualizar texto do botão com spinner
        const originalButtonText = saveAllBtn.innerHTML;
        saveAllBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Processando...';

        try {
            // CORREÇÃO PRINCIPAL: Obter apenas entradas ATIVAS que existem no DOM
            const allEntries = Array.from(batchContainer.querySelectorAll('.batch-entry'));
            const activeEntries = allEntries.filter(entry => {
                // Verificar se a entrada está marcada como ativa E ainda está no DOM
                const isActive = entry.getAttribute('data-entry-active') === 'true';
                const isInDOM = document.contains(entry);
                const isNotRemoving = !entry.classList.contains('removing');
                
                return isActive && isInDOM && isNotRemoving;
            });

            if (activeEntries.length === 0) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Atenção',
                    text: 'Adicione pelo menos uma entrada antes de salvar',
                    confirmButtonColor: '#fec32e'
                });
                return;
            }

            // Criar array para armazenar os dados válidos
            const validEntries = [];
            let hasInvalidEntries = false;

            // Validar cada entrada ATIVA
            activeEntries.forEach((entry, index) => {
                const paymentDetail = entry.querySelector('.batch-payment-detail');
                const amount = entry.querySelector('.batch-amount');
                const description = entry.querySelector('.batch-description');

                // Verificar se os elementos ainda existem (proteção extra)
                if (!paymentDetail || !amount || !description) {
                    console.warn(`Entrada ${index + 1} não tem todos os elementos necessários`);
                    return;
                }

                // Resetar classes de validação
                paymentDetail.classList.remove('is-invalid');
                amount.classList.remove('is-invalid');

                // Validar campos
                let isEntryValid = true;

                if (!paymentDetail.value) {
                    isEntryValid = false;
                    hasInvalidEntries = true;
                    paymentDetail.classList.add('is-invalid');
                }

                const amountValue = parseFloat(amount.value);
                if (!amount.value || isNaN(amountValue) || amountValue <= 0) {
                    isEntryValid = false;
                    hasInvalidEntries = true;
                    amount.classList.add('is-invalid');
                }

                // Se a entrada for válida, adicionar ao array
                if (isEntryValid) {
                    validEntries.push({
                        payment_method: paymentDetail.value,
                        amount: amountValue,
                        description: description.value || ''
                    });
                }
            });

            if (hasInvalidEntries) {
                Swal.fire({
                    icon: 'error',
                    title: 'Erro',
                    text: 'Preencha todos os campos obrigatórios corretamente',
                    confirmButtonColor: '#fec32e'
                });
                return;
            }

            if (validEntries.length === 0) {
                Swal.fire({
                    icon: 'warning',
                    title: 'Atenção',
                    text: 'Nenhuma entrada válida para processar',
                    confirmButtonColor: '#fec32e'
                });
                return;
            }

            // Criar objeto com os dados para enviar
            const dataToSend = {
                entries: validEntries,
                date: document.getElementById('currentDateValue').value
            };

            // Enviar via fetch API como JSON
            const response = await fetch(batchForm.action, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Requested-With': 'XMLHttpRequest'
                },
                body: JSON.stringify(dataToSend)
            });

            if (!response.ok) {
                throw new Error('Erro na resposta do servidor');
            }

            const data = await response.json();

            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Sucesso',
                    text: data.message,
                    confirmButtonColor: '#fec32e'
                }).then(() => {
                    // Limpar o formulário
                    batchContainer.innerHTML = '';
                    entryIdCounter = 0;
                    lastPaymentMethod = null;
                    lastPaymentDetail = null;

                    // Recarregar a página mantendo a data
                    const currentUrl = new URL(window.location.href);
                    currentUrl.searchParams.set('date', document.getElementById('currentDateValue').value);
                    window.location.href = currentUrl.toString();
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Erro',
                    text: data.message,
                    confirmButtonColor: '#fec32e'
                });
            }

        } catch (error) {
            console.error('Erro ao salvar movimentações:', error);
            Swal.fire({
                icon: 'error',
                title: 'Erro',
                text: 'Ocorreu um erro ao salvar as movimentações. Por favor, tente novamente.',
                confirmButtonColor: '#fec32e'
            });
        } finally {
            // NOVO: Reabilitar todos os elementos
            isProcessing = false;
            addEntryBtn.disabled = false;
            saveAllBtn.disabled = false;
            saveAllBtn.innerHTML = originalButtonText;
            
            // Reabilitar botões de remoção
            const removeButtons = batchContainer.querySelectorAll('.remove-entry');
            removeButtons.forEach(btn => btn.disabled = false);
        }
    });
}

// Ativa spinner/disable no botão do formulário principal
function initializeSingleMovementForm() {
    const form   = document.querySelector('#register form');
    const button = document.getElementById('registerMovementBtn');

    if (!form || !button) return;

    form.addEventListener('submit', () => {
        button.disabled = true;
        button.innerHTML =
            '<span class="spinner-border spinner-border-sm me-2"></span>Processando...';
    });
}