class NationRankings {
    constructor() {
        this.API_URL = "";  // Use relative URLs since we're on the same server
        this.init();
    }

    init() {
        this.bindElements();
        this.setupEventListeners();
        this.updateLastUpdated();
        this.updateRankings();
    }

    bindElements() {
        this.gameModeSelector = document.querySelector('.game-mode-selector');
        this.rankingBody = document.getElementById('rankingBody');
        this.rankingTitle = document.getElementById('rankingTitle');
        this.playerSearchInput = document.getElementById('playerSearchInput');
        this.searchResultsContainer = document.getElementById('searchResults');
    }

    setupEventListeners() {
        this.gameModeSelector.addEventListener('click', (e) => {
            if (e.target.tagName === 'BUTTON') {
                this.gameModeSelector.querySelector('button.active').classList.remove('active');
                e.target.classList.add('active');
                this.updateRankings();
                // Clear search when changing game mode
                this.playerSearchInput.value = '';
                this.searchResultsContainer.innerHTML = '';
            }
        });

        // Player search functionality
        this.playerSearchInput.addEventListener('input', Utils.debounce(() => this.handlePlayerSearch(), 300));

        // Click-to-toggle contributors
        this.rankingBody.addEventListener('click', (e) => {
            const nationRow = e.target.closest('.nation-row');
            if (!nationRow) return;
            
            const code = nationRow.dataset.countryCode;
            const contributorsRow = document.getElementById(`contributors-${code}`);
            if (contributorsRow) {
                const isVisible = contributorsRow.style.display === 'table-row';
                contributorsRow.style.display = isVisible ? 'none' : 'table-row';
            }
        });
    }

    updateLastUpdated() {
        const now = new Date();
        const formattedTime = now.toLocaleString('en-US', {
            year: 'numeric',
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit'
        });
        
        const lastUpdatedElement = document.getElementById('lastUpdated');
        if (lastUpdatedElement) {
            lastUpdatedElement.textContent = `Last updated: ${formattedTime}`;
        }
    }

    async updateRankings() {
        const gameMode = this.gameModeSelector.querySelector('button.active').dataset.mode;
        this.rankingTitle.textContent = `Loading...`;
        Utils.showMessage(this.rankingBody, 'Loading rankings...');

        try {
            const response = await fetch(`${this.API_URL}/api/nation-rankings/${encodeURIComponent(gameMode)}`);
            const data = await response.json();
            this.rankingTitle.textContent = `Nation Rankings - ${gameMode}`;
            this.displayRankings(data);
            this.updateLastUpdated(); // Update timestamp when data is refreshed
        } catch (error) {
            console.error("Failed to fetch nation rankings:", error);
            this.rankingTitle.textContent = "Error";
            Utils.showMessage(this.rankingBody, 'Error loading data. Check console for details.', true);
        }
    }

    displayRankings(rankings) {
        this.rankingBody.innerHTML = "";
        if (!rankings || rankings.length === 0) {
            Utils.showMessage(this.rankingBody, 'No ranking data found for this game mode.');
            return;
        }

        rankings.forEach(nation => {
            // Create the nation row
            const row = document.createElement('tr');
            row.className = 'nation-row';
            row.dataset.countryCode = nation.countryCode;

            const { scoreClass, scoreSign } = Utils.formatScore(nation.total_score);
            
            // Get current game mode for the View Details button
            const currentGameMode = this.gameModeSelector.querySelector('button.active').dataset.mode;

            row.innerHTML = `
                <td class="rank">${nation.rank}</td>
                <td>
                    ${nation.country_name || nation.countryCode}
                    <button class="view-details-btn" onclick="window.nationRankings.showScoreBreakdown('${nation.countryCode}', '${currentGameMode}')">
                        View Details
                    </button>
                </td>
                <td class="${scoreClass}">${scoreSign}${Math.round(nation.total_score)}</td>
            `;
            this.rankingBody.appendChild(row);

            // Add contributors if available
            const contribs = nation.top_contributors || nation.topContributors;
            if (Array.isArray(contribs) && contribs.length > 0) {
                const contributorsRow = document.createElement('tr');
                contributorsRow.className = 'contributors-row';
                contributorsRow.id = `contributors-${nation.countryCode}`;

                const contributorsHTML = `
                    <table class="contributors-table">
                        <tr><th colspan="2">Top Weekly Contributors</th></tr>
                        ${contribs.map(p => {
                            const { scoreClass: pScoreClass, scoreSign: pScoreSign } = Utils.formatScore(p.score);
                            return `
                                <tr>
                                    <td class="player-name">${p.name}</td>
                                    <td class="${pScoreClass}">${pScoreSign}${p.score}</td>
                                </tr>
                            `;
                        }).join('')}
                    </table>`;

                const cell = document.createElement('td');
                cell.colSpan = 3;
                cell.className = 'contributors-cell';
                cell.innerHTML = contributorsHTML;
                contributorsRow.appendChild(cell);
                this.rankingBody.appendChild(contributorsRow);
            }
        });
    }

    async showScoreBreakdown(countryCode, gameMode) {
        try {
            const response = await fetch(`${this.API_URL}/api/nation-score-breakdown/${countryCode}/${encodeURIComponent(gameMode)}`);
            const data = await response.json();
            
            if (!response.ok) {
                throw new Error(data.error || 'Failed to fetch breakdown');
            }
            
            this.displayScoreBreakdownModal(data);
        } catch (error) {
            console.error('Error fetching score breakdown:', error);
            alert('Failed to load score breakdown: ' + error.message);
        }
    }

    displayScoreBreakdownModal(data) {
        // Create modal if it doesn't exist
        let modal = document.getElementById('scoreBreakdownModal');
        if (!modal) {
            modal = document.createElement('div');
            modal.id = 'scoreBreakdownModal';
            modal.className = 'modal';
            document.body.appendChild(modal);
        }

        const modalContent = `
            <div class="modal-content">
                <div class="modal-header">
                    <h2>Score Breakdown: ${data.country_name} (${data.country_code}) - ${data.game_type}</h2>
                    <button class="modal-close" onclick="document.getElementById('scoreBreakdownModal').style.display='none'">&times;</button>
                </div>
                
                <div class="breakdown-section">
                    <h3>Scoring System</h3>
                    <p>${data.explanation.scoring_system}</p>
                    <p><strong>Calculation:</strong> ${data.explanation.calculation}</p>
                    <div class="confidence-details">
                        <p><strong>Confidence Factor Formula:</strong></p>
                        <div class="formula-explanation">
                            <strong>k = Average Games per Nation ÷ 2 = ${data.handicap_info.k_value}</strong><br>
                            <strong>Confidence Factor = 2k = ${data.handicap_info.confidence_factor}</strong>
                        </div>
                        <p><em>${data.explanation.interpretation}</em></p>
                    </div>
                    <p><small>${data.explanation.comparison}</small></p>
                </div>

                <div class="breakdown-section">
                    <h3>Overall Statistics</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value ${data.adjusted_score >= 0 ? 'positive' : 'negative'}">${data.adjusted_score >= 0 ? '+' : ''}${Math.round(data.adjusted_score)}</div>
                            <div class="stat-label">Adjusted Score</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.total_players}</div>
                            <div class="stat-label">Total Players</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.total_games}</div>
                            <div class="stat-label">Total Games</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.handicap_info.confidence_factor}</div>
                            <div class="stat-label">Confidence Factor</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value ${data.handicap_info.meets_minimum ? 'positive' : 'negative'}">${data.handicap_info.min_games_required}</div>
                            <div class="stat-label">Min Games Required</div>
                        </div>
                    </div>
                    <div class="minimum-games-status">
                        ${data.handicap_info.meets_minimum 
                            ? `<span class="status-success">✓ Meets minimum games requirement (${data.total_games} ≥ ${data.handicap_info.min_games_required})</span>`
                            : `<span class="status-warning">⚠ Below minimum games threshold (${data.total_games} < ${data.handicap_info.min_games_required})</span>`
                        }
                    </div>
                </div>

                <div class="breakdown-section">
                    <h3>Score Comparison</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value ${data.raw_percentage >= 0 ? 'positive' : 'negative'}">${data.raw_percentage >= 0 ? '+' : ''}${Math.round(data.raw_percentage)}</div>
                            <div class="stat-label">Raw Win Rate</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value ${data.adjusted_score >= 0 ? 'positive' : 'negative'}">${data.adjusted_score >= 0 ? '+' : ''}${Math.round(data.adjusted_score)}</div>
                            <div class="stat-label">Confidence Adjusted</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.handicap_info.k_value}</div>
                            <div class="stat-label">K Value</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value positive">${data.score_breakdown.win_rate_percentage}%</div>
                            <div class="stat-label">Win Rate</div>
                        </div>
                    </div>
                </div>

                <div class="breakdown-section">
                    <h3>Game Results</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value positive">${data.score_breakdown.total_wins}</div>
                            <div class="stat-label">Total Wins</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value negative">${data.score_breakdown.total_losses}</div>
                            <div class="stat-label">Total Losses</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value ${data.raw_score >= 0 ? 'positive' : 'negative'}">${data.raw_score >= 0 ? '+' : ''}${data.raw_score}</div>
                            <div class="stat-label">Net Result</div>
                        </div>
                    </div>
                </div>

                <div class="breakdown-section">
                    <h3>Player Distribution</h3>
                    <div class="stats-grid">
                        <div class="stat-card">
                            <div class="stat-value positive">${data.player_distribution.positive_players}</div>
                            <div class="stat-label">Players with Net Wins</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value negative">${data.player_distribution.negative_players}</div>
                            <div class="stat-label">Players with Net Losses</div>
                        </div>
                        <div class="stat-card">
                            <div class="stat-value">${data.player_distribution.zero_players}</div>
                            <div class="stat-label">Players with Even W/L</div>
                        </div>
                    </div>
                </div>

                ${data.top_contributors.length > 0 ? `
                <div class="breakdown-section">
                    <h3>Top Contributors (Most Wins)</h3>
                    <table>
                        <thead>
                            <tr>
                                <th>Player</th>
                                <th>Net Score</th>
                                <th>Wins</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${data.top_contributors.map(player => `
                                <tr>
                                    <td>${player.name}</td>
                                    <td class="positive">+${player.score}</td>
                                    <td>${player.wins}</td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
                ` : ''}
            </div>
        `;

        modal.innerHTML = modalContent;
        modal.style.display = 'block';

        // Close modal when clicking outside
        modal.onclick = (e) => {
            if (e.target === modal) {
                modal.style.display = 'none';
            }
        };
    }

    async handlePlayerSearch() {
        const searchTerm = this.playerSearchInput.value.trim();
        
        if (searchTerm.length < 2) {
            this.searchResultsContainer.innerHTML = '';
            return;
        }

        const gameMode = this.gameModeSelector.querySelector('button.active').dataset.mode;
        
        try {
            const response = await fetch(`${this.API_URL}/api/search-player/${encodeURIComponent(gameMode)}/${encodeURIComponent(searchTerm)}`);
            const data = await response.json();
            
            this.displaySearchResults(data);
        } catch (error) {
            console.error('Error searching for player:', error);
            this.searchResultsContainer.innerHTML = '<div class="error">Search failed. Please try again.</div>';
        }
    }

    displaySearchResults(results) {
        if (!results || results.length === 0) {
            this.searchResultsContainer.innerHTML = '<div class="no-results">No players found matching your search.</div>';
            return;
        }

        const resultsHTML = `
            <div class="search-results">
                <h3>Search Results</h3>
                ${results.map(player => `
                    <div class="search-result-item">
                        <div class="player-info">
                            <strong>${player.player_name}</strong>
                            <span class="total-score ${player.total_score >= 0 ? 'positive' : 'negative'}">
                                Total Score: ${player.total_score >= 0 ? '+' : ''}${player.total_score}
                            </span>
                        </div>
                        <div class="player-contributions">
                            ${player.contributions.map(contrib => `
                                <div class="contribution-item">
                                    <span class="country">${contrib.country_name}</span>
                                    <span class="score ${contrib.score >= 0 ? 'positive' : 'negative'}">
                                        ${contrib.score >= 0 ? '+' : ''}${contrib.score}
                                    </span>
                                </div>
                            `).join('')}
                        </div>
                    </div>
                `).join('')}
            </div>
        `;

        this.searchResultsContainer.innerHTML = resultsHTML;
    }
}

// Toggle explanation function for info box
function toggleExplanation() {
    const explanation = document.getElementById('detailedExplanation');
    const icon = document.querySelector('.toggle-icon');
    const text = document.querySelector('.toggle-text');
    
    if (explanation.style.display === 'none') {
        explanation.style.display = 'block';
        icon.textContent = '▼';
        text.textContent = 'Hide detailed explanation';
    } else {
        explanation.style.display = 'none';
        icon.textContent = '▶';
        text.textContent = 'Show detailed explanation';
    }
}

// Initialize when DOM is loaded
document.addEventListener('DOMContentLoaded', () => {
    window.nationRankings = new NationRankings();
    // Make toggle function globally available
    window.toggleExplanation = toggleExplanation;
});
