// Script principal para funcionalidades comuns

// Função para mascarar CPF
function maskCPF(input) {
    let value = input.value.replace(/\D/g, '');
    if (value.length <= 11) {
        value = value.replace(/(\d{3})(\d)/, '$1.$2');
        value = value.replace(/(\d{3})(\d)/, '$1.$2');
        value = value.replace(/(\d{3})(\d{1,2})$/, '$1-$2');
    }
    input.value = value;
}

// Função para mascarar telefone
function maskPhone(input) {
    let value = input.value.replace(/\D/g, '');
    if (value.length <= 11) {
        if (value.length > 2) {
            value = '(' + value.substring(0, 2) + ') ' + value.substring(2);
        }
        if (value.length > 10) {
            value = value.substring(0, 10) + '-' + value.substring(10);
        }
    }
    input.value = value;
}

// Formatação de valores monetários
function formatCurrency(value) {
    return parseFloat(value).toLocaleString('pt-BR', {
        style: 'currency',
        currency: 'BRL'
    });
}

// Confirmar exclusão de registros
function confirmDelete(message) {
    return confirm(message || 'Tem certeza que deseja excluir este registro?');
}

// Exibir mensagem de sucesso
function showSuccess(message) {
    Swal.fire({
        icon: 'success',
        title: 'Sucesso!',
        text: message,
        timer: 3000,
        showConfirmButton: false
    });
}

// Exibir mensagem de erro
function showError(message) {
    Swal.fire({
        icon: 'error',
        title: 'Erro!',
        text: message
    });
}

// Exibir confirmação
function showConfirm(title, text, callback) {
    Swal.fire({
        title: title,
        text: text,
        icon: 'question',
        showCancelButton: true,
        confirmButtonColor: '#FEC32E',
        cancelButtonColor: '#f74d3e',
        confirmButtonText: 'Sim',
        cancelButtonText: 'Cancelar'
    }).then((result) => {
        if (result.isConfirmed && typeof callback === 'function') {
            callback();
        }
    });
}

// Inicializa máscaras para campos quando a página carrega
document.addEventListener('DOMContentLoaded', function() {
    // Aplicar máscaras aos campos de CPF
    const cpfInputs = document.querySelectorAll('input[data-mask="cpf"]');
    cpfInputs.forEach(input => {
        input.addEventListener('input', function() {
            maskCPF(this);
        });
    });

    // Aplicar máscaras aos campos de telefone
    const phoneInputs = document.querySelectorAll('input[data-mask="phone"]');
    phoneInputs.forEach(input => {
        input.addEventListener('input', function() {
            maskPhone(this);
        });
    });
});