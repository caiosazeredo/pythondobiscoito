/**
 * Sistema de Calendário para Caixas
 * Gerencia navegação por datas e atualização de dados
 */

class CashiersCalendar {
    constructor() {
        this.unitId = null;
        this.currentDate = null;
        this.isLoading = false;
        this.elements = {};
        
        this.init();
    }
    
    init() {
        this.initializeElements();
        this.initializeEventListeners();
        this.setupKeyboardNavigation();
        
        // Obter ID da unidade da URL
        const urlParts = window.location.pathname.split('/');
        const unitIndex = urlParts.indexOf('unit');
        if (unitIndex !== -1 && urlParts[unitIndex + 1]) {
            this.unitId = urlParts[unitIndex + 1];
        }
        
        console.log('Calendário de Caixas inicializado para unidade:', this.unitId);
    }
    
    initializeElements() {
        this.elements = {
            dateSelector: document.getElementById('dateSelector'),
            todayBtn: document.getElementById('todayBtn'),
            loadingOverlay: document.getElementById('loadingOverlay'),
            selectedDateDisplay: document.getElementById('selectedDateDisplay'),
            
            // Elementos de valores
            baseAmountDisplay: document.getElementById('baseAmountDisplay'),
            dinheiroPixDisplay: document.getElementById('dinheiroPixDisplay'),
            coinsAmountDisplay: document.getElementById('coinsAmountDisplay'),
            totalZDisplay: document.getElementById('totalZDisplay'),
            
            // Container dos caixas
            cashiersContainer: document.getElementById('cashiersContainer')
        };
        
        // Verificar se os elementos existem
        Object.keys(this.elements).forEach(key => {
            if (!this.elements[key]) {
                console.warn(`Elemento ${key} não encontrado`);
            }
        });
    }
    
    initializeEventListeners() {
        // Event listener para mudança de data
        if (this.elements.dateSelector) {
            this.elements.dateSelector.addEventListener('change', (e) => {
                this.navigateToDate(e.target.value);
            });
        }
        
        // Botão "Hoje"
        if (this.elements.todayBtn) {
            this.elements.todayBtn.addEventListener('click', () => {
                this.goToToday();
            });
        }
        
        // Prevenir recarregamento desnecessário da página
        window.addEventListener('beforeunload', () => {
            this.hideLoading();
        });
    }
    
    setupKeyboardNavigation() {
        if (!this.elements.dateSelector) return;
        
        this.elements.dateSelector.addEventListener('keydown', (e) => {
            if (this.isLoading) {
                e.preventDefault();
                return;
            }
            
            const currentDate = new Date(this.elements.dateSelector.value || new Date());
            let newDate;
            
            switch(e.key) {
                case 'ArrowLeft':
                    e.preventDefault();
                    newDate = new Date(currentDate);
                    newDate.setDate(currentDate.getDate() - 1);
                    break;
                case 'ArrowRight':
                    e.preventDefault();
                    newDate = new Date(currentDate);
                    newDate.setDate(currentDate.getDate() + 1);
                    break;
                case 'ArrowUp':
                    e.preventDefault();
                    newDate = new Date(currentDate);
                    newDate.setDate(currentDate.getDate() - 7);
                    break;
                case 'ArrowDown':
                    e.preventDefault();
                    newDate = new Date(currentDate);
                    newDate.setDate(currentDate.getDate() + 7);
                    break;
                case 'Home':
                    e.preventDefault();
                    this.goToToday();
                    return;
                default:
                    return;
            }
            
            if (newDate) {
                const newDateString = newDate.toISOString().split('T')[0];
                this.elements.dateSelector.value = newDateString;
                this.navigateToDate(newDateString);
            }
        });
        
        // Tooltip com instruções
        this.elements.dateSelector.title = "Navegação: ←→ (dias), ↑↓ (semanas), Home (hoje)";
    }
    
    showLoading() {
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.classList.remove('d-none');
        }
        this.isLoading = true;
        
        // Adicionar classe de loading aos valores
        this.addLoadingToValues();
    }
    
    hideLoading() {
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.classList.add('d-none');
        }
        this.isLoading = false;
        
        // Remover classe de loading dos valores
        this.removeLoadingFromValues();
    }
    
    addLoadingToValues() {
        const valueElements = [
            this.elements.baseAmountDisplay,
            this.elements.dinheiroPixDisplay,
            this.elements.coinsAmountDisplay,
            this.elements.totalZDisplay
        ];
        
        valueElements.forEach(element => {
            if (element) {
                element.classList.add('value-loading');
            }
        });
    }
    
    removeLoadingFromValues() {
        const valueElements = [
            this.elements.baseAmountDisplay,
            this.elements.dinheiroPixDisplay,
            this.elements.coinsAmountDisplay,
            this.elements.totalZDisplay
        ];
        
        valueElements.forEach(element => {
            if (element) {
                element.classList.remove('value-loading');
            }
        });
    }
    
    formatCurrency(value) {
        return 'R$ ' + parseFloat(value).toFixed(2).replace('.', ',').replace(/\B(?=(\d{3})+(?!\d))/g, '.');
    }
    
    formatDateForDisplay(dateString) {
        const date = new Date(dateString + 'T00:00:00');
        return date.toLocaleDateString('pt-BR');
    }
    
    navigateToDate(selectedDate, useAPI = true) {
        if (!selectedDate || this.isLoading) return;
        
        this.currentDate = selectedDate;
        this.showLoading();
        
        // Atualizar display da data
        if (this.elements.selectedDateDisplay) {
            this.elements.selectedDateDisplay.textContent = this.formatDateForDisplay(selectedDate);
        }
        
        if (useAPI && this.unitId) {
            // Usar API para carregamento mais rápido
            this.loadDataViaAPI(selectedDate)
                .then(success => {
                    if (!success) {
                        // Se a API falhar, fazer reload da página
                        this.navigateToDateWithReload(selectedDate);
                    }
                })
                .catch(() => {
                    // Em caso de erro, fazer reload da página
                    this.navigateToDateWithReload(selectedDate);
                });
        } else {
            // Reload da página como fallback
            this.navigateToDateWithReload(selectedDate);
        }
    }
    
    navigateToDateWithReload(selectedDate) {
        const url = new URL(window.location.href);
        url.searchParams.set('date', selectedDate);
        window.location.href = url.toString();
    }
    
    async loadDataViaAPI(selectedDate) {
        try {
            const response = await fetch(`/api/unit/${this.unitId}/cashiers_data?date=${selectedDate}`);
            
            if (!response.ok) {
                throw new Error('Resposta da API não foi bem-sucedida');
            }
            
            const result = await response.json();
            
            if (result.success) {
                this.updatePageWithData(result.data);
                this.updateDateBadge(selectedDate);
                this.hideLoading();
                return true;
            } else {
                throw new Error(result.error || 'Erro na resposta da API');
            }
            
        } catch (error) {
            console.error('Erro ao carregar dados via API:', error);
            return false;
        }
    }
    
    updatePageWithData(data) {
        // Atualizar valores de resumo
        if (this.elements.baseAmountDisplay) {
            this.elements.baseAmountDisplay.textContent = this.formatCurrency(data.base_amount);
        }
        
        if (this.elements.dinheiroPixDisplay) {
            this.elements.dinheiroPixDisplay.textContent = this.formatCurrency(data.saldo_dinheiro_dia);
            
            // Atualizar classe de cor
            this.elements.dinheiroPixDisplay.className = data.saldo_dinheiro_dia >= 0 ? 'text-success' : 'text-danger';
        }
        
        if (this.elements.coinsAmountDisplay) {
            this.elements.coinsAmountDisplay.textContent = this.formatCurrency(data.coins_amount);
        }
        
        if (this.elements.totalZDisplay) {
            this.elements.totalZDisplay.textContent = this.formatCurrency(data.total_z);
        }
        
        // Atualizar dados dos caixas
        this.updateCashiersData(data.cashiers, data.financial_balance, data.base_amount, data.saldo_dinheiro_dia);
        
        // Atualizar URL sem reload
        const url = new URL(window.location.href);
        url.searchParams.set('date', data.selected_date);
        window.history.replaceState({}, '', url.toString());
    }
    
    updateCashiersData(cashiers, financialBalance, baseAmount, saldoDinheiroDia) {
        // Atualizar caixa financeiro
        const financialCard = document.querySelector('.card.border-warning');
        if (financialCard) {
            const baseValue = financialCard.querySelector('.fw-bold.text-primary');
            const dinheiroValue = financialCard.querySelector('.fw-bold.text-success, .fw-bold.text-danger');
            const saldoValue = financialCard.querySelector('.small.text-success, .small.text-danger');
            
            if (baseValue) baseValue.textContent = this.formatCurrency(baseAmount);
            
            if (dinheiroValue) {
                dinheiroValue.textContent = this.formatCurrency(saldoDinheiroDia);
                dinheiroValue.className = saldoDinheiroDia >= 0 ? 'fw-bold text-success' : 'fw-bold text-danger';
            }
            
            if (saldoValue) {
                saldoValue.textContent = this.formatCurrency(financialBalance);
                saldoValue.className = financialBalance >= 0 ? 'small text-success' : 'small text-danger';
            }
        }
        
        // Atualizar caixas regulares
        cashiers.forEach(cashier => {
            if (cashier.number > 0) {
                const cashierCard = document.querySelector(`[data-number="${cashier.number}"]`);
                if (cashierCard) {
                    // Atualizar status
                    const statusBadge = cashierCard.querySelector('.badge');
                    if (statusBadge) {
                        statusBadge.textContent = cashier.status === 'aberto' ? 'Aberto' : 'Fechado';
                        statusBadge.className = cashier.status === 'aberto' ? 'badge rounded-pill bg-success' : 'badge rounded-pill bg-danger';
                    }
                    
                    // Atualizar valores
                    const values = cashierCard.querySelectorAll('.d-flex.justify-content-between span:last-child');
                    if (values.length >= 4) {
                        // Entradas
                        values[1].textContent = this.formatCurrency(cashier.entrada);
                        values[1].className = 'text-success';
                        
                        // Estornos (se houver)
                        if (cashier.estorno > 0) {
                            let estornoElement = cashierCard.querySelector('.text-danger');
                            if (!estornoElement) {
                                // Criar elemento de estorno se não existir
                                // Esta é uma simplificação - idealmente recriaria toda a estrutura
                            } else {
                                estornoElement.textContent = this.formatCurrency(cashier.estorno);
                            }
                        }
                        
                        // Saldo
                        const saldoElement = values[values.length - 1];
                        saldoElement.textContent = this.formatCurrency(cashier.saldo);
                        saldoElement.className = cashier.saldo >= 0 ? 'fw-bold text-success' : 'fw-bold text-danger';
                    }
                    
                    // Atualizar data-status para busca
                    cashierCard.setAttribute('data-status', cashier.status);
                }
            }
        });
    }
    
    updateDateBadge(selectedDate) {
        const today = new Date().toISOString().split('T')[0];
        const badge = document.querySelector('.badge.bg-warning, .badge.bg-info');
        
        if (badge && this.elements.selectedDateDisplay) {
            if (selectedDate !== today) {
                badge.classList.remove('bg-warning', 'text-dark');
                badge.classList.add('bg-info', 'text-white');
                badge.innerHTML = '<i class="bi bi-calendar-event me-2"></i>Dados de: ' + 
                    this.elements.selectedDateDisplay.textContent + ' <small>(não é hoje)</small>';
            } else {
                badge.classList.remove('bg-info', 'text-white');
                badge.classList.add('bg-warning', 'text-dark');
                badge.innerHTML = '<i class="bi bi-calendar-check me-2"></i>Dados de: ' + 
                    this.elements.selectedDateDisplay.textContent;
            }
        }
    }
    
    goToToday() {
        const today = new Date().toISOString().split('T')[0];
        if (this.elements.dateSelector) {
            this.elements.dateSelector.value = today;
        }
        this.navigateToDate(today);
    }
    
    // Método público para navegação programática
    setDate(dateString) {
        if (this.elements.dateSelector) {
            this.elements.dateSelector.value = dateString;
        }
        this.navigateToDate(dateString);
    }
    
    // Método para obter a data atual
    getCurrentDate() {
        return this.currentDate;
    }
}

// Inicializar quando o DOM estiver pronto
let cashiersCalendar;

document.addEventListener('DOMContentLoaded', function() {
    // Verificar se estamos na página correta
    if (window.location.pathname.includes('/cashiers')) {
        cashiersCalendar = new CashiersCalendar();
        
        // Tornar disponível globalmente para debugging
        window.cashiersCalendar = cashiersCalendar;
    }
});

// Exportar para uso em outros scripts se necessário
if (typeof module !== 'undefined' && module.exports) {
    module.exports = CashiersCalendar;
}