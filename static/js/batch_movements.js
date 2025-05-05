// Script para registro de movimentações em lote
document.addEventListener('DOMContentLoaded', function() {
    const batchForm = document.getElementById('batchMovementsForm');
    const batchContainer = document.getElementById('batchEntriesContainer');
    const addEntryBtn = document.getElementById('addBatchEntry');
    const saveAllBtn = document.getElementById('saveBatchEntries');
    
    if (!batchForm || !batchContainer || !addEntryBtn || !saveAllBtn) {
        return; // Sair se não estiver na página correta
    }
    
    let entryCount = 0;
    let lastPaymentMethod = null;
    
    // Função para adicionar uma nova linha de entrada
    function addBatchEntry() {
        entryCount++;
        
        const entryRow = document.createElement('div');
        entryRow.className = 'batch-entry row mb-2 border-bottom pb-2';
        entryRow.setAttribute('data-entry-id', entryCount);
        
        let paymentMethodOptions = '<option value="">Selecione</option>';
        
        // Usar o último método de pagamento como default se existir
        if (lastPaymentMethod) {
            const paymentMethods = document.querySelectorAll('#payment_method_main option');
            paymentMethods.forEach(option => {
                if (option.value) {
                    if (option.value === lastPaymentMethod) {
                        paymentMethodOptions += `<option value="${option.value}" data-category="${option.getAttribute('data-category')}" selected>${option.textContent}</option>`;
                    } else {
                        paymentMethodOptions += `<option value="${option.value}" data-category="${option.getAttribute('data-category')}">${option.textContent}</option>`;
                    }
                }
            });
        } else {
            const paymentMethods = document.querySelectorAll('#payment_method_main option');
            paymentMethods.forEach(option => {
                if (option.value) {
                    paymentMethodOptions += `<option value="${option.value}" data-category="${option.getAttribute('data-category')}">${option.textContent}</option>`;
                }
            });
        }
        
        entryRow.innerHTML = `
            <div class="col-md-3">
                <select class="form-select batch-payment-method" name="batch_payment_method_${entryCount}" required>
                    ${paymentMethodOptions}
                </select>
            </div>
            <div class="col-md-3">
                <select class="form-select batch-payment-detail" name="batch_payment_detail_${entryCount}" required>
                    <option value="">Selecione o tipo primeiro</option>
                </select>
            </div>
            <div class="col-md-2">
                <div class="input-group">
                    <span class="input-group-text">R$</span>
                    <input type="number" class="form-control batch-amount" name="batch_amount_${entryCount}" step="0.01" min="0.01" required>
                </div>
            </div>
            <div class="col-md-3">
                <input type="text" class="form-control batch-description" name="batch_description_${entryCount}" placeholder="Descrição (opcional)">
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
        paymentMethodSelect.addEventListener('change', function() {
            if (this.value) {
                lastPaymentMethod = this.value;
                loadPaymentDetails(this.value, paymentDetailSelect);
            } else {
                paymentDetailSelect.innerHTML = '<option value="">Selecione o tipo primeiro</option>';
            }
        });
        
        // Disparar o evento de change se tiver valor inicial
        if (paymentMethodSelect.value) {
            paymentMethodSelect.dispatchEvent(new Event('change'));
        }
        
        // Remover entrada
        removeBtn.addEventListener('click', function() {
            entryRow.remove();
        });
        
        // Permitir adicionar nova linha ao pressionar Enter no campo de valor
        amountInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                
                // Verificar se o campo de valor está preenchido
                if (this.value && parseFloat(this.value) > 0) {
                    addBatchEntry();
                } else {
                    // Mostrar mensagem de erro
                    Swal.fire({
                        icon: 'warning',
                        title: 'Atenção',
                        text: 'Preencha o valor antes de adicionar uma nova linha',
                        confirmButtonColor: '#fec32e'
                    });
                }
            }
        });
    }
    
    // Função para carregar opções detalhadas de pagamento
    function loadPaymentDetails(parentId, selectElement) {
        fetch(`/api/payment_methods/${parentId}`)
            .then(response => response.json())
            .then(data => {
                selectElement.innerHTML = '';
                
                if (data.length === 0) {
                    // Se não houver subcategorias, usa o próprio método principal
                    const option = document.createElement('option');
                    option.value = parentId;
                    
                    // Encontrar o texto do método principal
                    const mainSelect = document.querySelector(`[data-entry-id="${selectElement.closest('.batch-entry').getAttribute('data-entry-id')}"] .batch-payment-method`);
                    option.textContent = mainSelect.options[mainSelect.selectedIndex].textContent;
                    
                    selectElement.appendChild(option);
                } else {
                    // Adiciona opção padrão
                    const defaultOption = document.createElement('option');
                    defaultOption.value = '';
                    defaultOption.textContent = 'Selecione';
                    selectElement.appendChild(defaultOption);
                    
                    // Adiciona subcategorias
                    data.forEach(method => {
                        const option = document.createElement('option');
                        option.value = method.id;
                        option.textContent = method.name;
                        selectElement.appendChild(option);
                    });
                }
            })
            .catch(error => console.error('Erro ao carregar formas de pagamento:', error));
    }
    
    // Adicionar primeira entrada ao carregar a página
    addEntryBtn.addEventListener('click', addBatchEntry);
    
    // Adicionar entrada inicial
    addBatchEntry();
    
    // Salvar todas as entradas
    saveAllBtn.addEventListener('click', function() {
        // Verificar se todos os campos obrigatórios estão preenchidos
        const requiredFields = batchContainer.querySelectorAll('select[required], input[required]');
        let isValid = true;
        
        requiredFields.forEach(field => {
            if (!field.value) {
                isValid = false;
                field.classList.add('is-invalid');
            } else {
                field.classList.remove('is-invalid');
            }
        });
        
        if (!isValid) {
            Swal.fire({
                icon: 'error',
                title: 'Erro',
                text: 'Preencha todos os campos obrigatórios',
                confirmButtonColor: '#fec32e'
            });
            return;
        }
        
        // Serializar o formulário
        const formData = new FormData(batchForm);
        
        // Adicionar informação sobre quantas entradas existem
        formData.append('entry_count', entryCount);
        
        // Enviar via fetch API
        fetch(batchForm.action, {
            method: 'POST',
            body: formData
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                Swal.fire({
                    icon: 'success',
                    title: 'Sucesso',
                    text: data.message,
                    confirmButtonColor: '#fec32e'
                }).then(() => {
                    // Recarregar a página para mostrar as novas entradas
                    window.location.reload();
                });
            } else {
                Swal.fire({
                    icon: 'error',
                    title: 'Erro',
                    text: data.message,
                    confirmButtonColor: '#fec32e'
                });
            }
        })
        .catch(error => {
            console.error('Erro ao salvar movimentações:', error);
            Swal.fire({
                icon: 'error',
                title: 'Erro',
                text: 'Ocorreu um erro ao salvar as movimentações',
                confirmButtonColor: '#fec32e'
            });
        });
    });
});