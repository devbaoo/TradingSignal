"""
Dynamic Correlation Clustering for Regime-Adaptive Asset Grouping
Replaces static sector lists with rolling correlation-based clustering.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple, Optional
import pandas as pd
import numpy as np
from sklearn.cluster import DBSCAN, KMeans
from sklearn.preprocessing import StandardScaler
import warnings

warnings.filterwarnings('ignore', category=RuntimeWarning)

logger = logging.getLogger(__name__)

@dataclass
class ClusteringConfig:
    """Configuration for dynamic correlation clustering."""
    lookback_candles: int = 200  # Rolling window for correlation calculation
    min_lookback: int = 90  # Minimum candles required
    correlation_threshold: float = 0.7  # Minimum correlation for grouping
    min_cluster_size: int = 3  # Minimum symbols per cluster
    max_cluster_size: int = 8  # Maximum symbols per cluster
    update_frequency: int = 20  # Update clusters every N candles
    stability_weight: float = 0.3  # Weight for cluster stability vs recency

@dataclass 
class ClusterInfo:
    """Information about a correlation cluster."""
    cluster_id: int
    symbols: Set[str]
    avg_correlation: float
    stability_score: float
    last_updated: int
    representative_symbol: str  # Symbol that best represents the cluster

class DynamicCorrelationClusterer:
    """Dynamic correlation-based clustering for risk management."""
    
    def __init__(self, config: Optional[ClusteringConfig] = None):
        self.config = config or ClusteringConfig()
        self.logger = logging.getLogger(__name__)
        self.clusters: Dict[int, ClusterInfo] = {}
        self.symbol_to_cluster: Dict[str, int] = {}
        self.correlation_history: Dict[Tuple[str, str], List[float]] = {}
        self.last_update_candle: int = 0
        self.price_history: Dict[str, List[float]] = {}
        
    def update_price_history(self, symbol_prices: Dict[str, float], candle_idx: int):
        """Update price history for correlation calculation."""
        for symbol, price in symbol_prices.items():
            if symbol not in self.price_history:
                self.price_history[symbol] = []
            
            self.price_history[symbol].append(price)
            
            # Keep only required lookback
            if len(self.price_history[symbol]) > self.config.lookback_candles:
                self.price_history[symbol] = self.price_history[symbol][-self.config.lookback_candles:]
    
    def calculate_rolling_correlations(self, symbols: List[str]) -> pd.DataFrame:
        """Calculate rolling correlation matrix for given symbols."""
        # Build price matrix
        price_data = {}
        min_length = float('inf')
        
        for symbol in symbols:
            if symbol in self.price_history and len(self.price_history[symbol]) >= self.config.min_lookback:
                prices = self.price_history[symbol]
                # Calculate returns
                returns = np.diff(np.log(prices)) if len(prices) > 1 else [0]
                price_data[symbol] = returns
                min_length = min(min_length, len(returns))
            else:
                self.logger.debug(f"Insufficient price history for {symbol}")
        
        if len(price_data) < 2 or min_length < self.config.min_lookback - 1:
            return pd.DataFrame()
        
        # Align lengths and create DataFrame
        aligned_data = {}
        for symbol, returns in price_data.items():
            aligned_data[symbol] = returns[-min_length:]
        
        df = pd.DataFrame(aligned_data)
        
        # Calculate correlation matrix
        try:
            correlation_matrix = df.corr()
            # Fill NaN with 0 (no correlation)
            correlation_matrix = correlation_matrix.fillna(0)
            return correlation_matrix
        except Exception as e:
            self.logger.error(f"Error calculating correlations: {e}")
            return pd.DataFrame()
    
    def detect_clusters_dbscan(self, correlation_matrix: pd.DataFrame) -> List[Set[str]]:
        """Use DBSCAN clustering on correlation matrix."""
        if correlation_matrix.empty:
            return []
        
        # Convert correlation to distance (1 - |correlation|)
        distance_matrix = 1 - np.abs(correlation_matrix.values)
        
        # Apply DBSCAN
        clustering = DBSCAN(
            eps=1 - self.config.correlation_threshold,  # Distance threshold
            min_samples=max(2, self.config.min_cluster_size - 1),
            metric='precomputed'
        )
        
        try:
            cluster_labels = clustering.fit_predict(distance_matrix)
            
            # Group symbols by cluster
            clusters = {}
            for idx, label in enumerate(cluster_labels):
                if label == -1:  # Noise/outlier
                    continue
                if label not in clusters:
                    clusters[label] = set()
                clusters[label].add(correlation_matrix.index[idx])
            
            # Filter by size constraints
            valid_clusters = []
            for cluster_symbols in clusters.values():
                if (self.config.min_cluster_size <= len(cluster_symbols) <= 
                    self.config.max_cluster_size):
                    valid_clusters.append(cluster_symbols)
            
            return valid_clusters
            
        except Exception as e:
            self.logger.error(f"DBSCAN clustering failed: {e}")
            return []
    
    def detect_clusters_kmeans(self, correlation_matrix: pd.DataFrame, n_clusters: int = None) -> List[Set[str]]:
        """Use K-means clustering as fallback method."""
        if correlation_matrix.empty or len(correlation_matrix) < 4:
            return []
        
        # Estimate number of clusters if not provided
        if n_clusters is None:
            n_symbols = len(correlation_matrix)
            n_clusters = max(2, min(n_symbols // self.config.min_cluster_size, 
                                   n_symbols // 2))
        
        try:
            # Use correlation matrix as features
            features = correlation_matrix.values
            
            # Standardize features
            scaler = StandardScaler()
            features_scaled = scaler.fit_transform(features)
            
            # Apply K-means
            kmeans = KMeans(n_clusters=n_clusters, random_state=42, n_init=10)
            cluster_labels = kmeans.fit_predict(features_scaled)
            
            # Group symbols by cluster
            clusters = {}
            for idx, label in enumerate(cluster_labels):
                if label not in clusters:
                    clusters[label] = set()
                clusters[label].add(correlation_matrix.index[idx])
            
            # Filter valid clusters
            valid_clusters = []
            for cluster_symbols in clusters.values():
                if len(cluster_symbols) >= self.config.min_cluster_size:
                    valid_clusters.append(cluster_symbols)
            
            return valid_clusters
            
        except Exception as e:
            self.logger.error(f"K-means clustering failed: {e}")
            return []
    
    def calculate_cluster_stats(self, cluster_symbols: Set[str], 
                              correlation_matrix: pd.DataFrame) -> Tuple[float, str]:
        """Calculate statistics for a cluster."""
        if len(cluster_symbols) < 2:
            return 0.0, list(cluster_symbols)[0] if cluster_symbols else ""
        
        # Calculate average correlation within cluster
        correlations = []
        symbols_list = list(cluster_symbols)
        
        for i in range(len(symbols_list)):
            for j in range(i + 1, len(symbols_list)):
                sym1, sym2 = symbols_list[i], symbols_list[j]
                if sym1 in correlation_matrix.index and sym2 in correlation_matrix.columns:
                    corr = abs(correlation_matrix.loc[sym1, sym2])
                    if not np.isnan(corr):
                        correlations.append(corr)
        
        avg_correlation = np.mean(correlations) if correlations else 0.0
        
        # Find representative symbol (highest average correlation to others)
        best_symbol = ""
        best_avg_corr = -1
        
        for symbol in symbols_list:
            if symbol not in correlation_matrix.index:
                continue
                
            symbol_correlations = []
            for other_symbol in symbols_list:
                if other_symbol != symbol and other_symbol in correlation_matrix.columns:
                    corr = abs(correlation_matrix.loc[symbol, other_symbol])
                    if not np.isnan(corr):
                        symbol_correlations.append(corr)
            
            if symbol_correlations:
                avg_corr = np.mean(symbol_correlations)
                if avg_corr > best_avg_corr:
                    best_avg_corr = avg_corr
                    best_symbol = symbol
        
        if not best_symbol and symbols_list:
            best_symbol = symbols_list[0]
        
        return avg_correlation, best_symbol
    
    def calculate_stability_score(self, new_cluster: Set[str], cluster_id: int) -> float:
        """Calculate stability score comparing to previous cluster."""
        if cluster_id not in self.clusters:
            return 0.5  # New cluster gets neutral stability
        
        old_cluster = self.clusters[cluster_id].symbols
        
        # Calculate Jaccard similarity
        intersection = len(new_cluster.intersection(old_cluster))
        union = len(new_cluster.union(old_cluster))
        
        jaccard = intersection / union if union > 0 else 0.0
        return jaccard
    
    def update_clusters(self, symbol_prices: Dict[str, float], candle_idx: int, 
                       force_update: bool = False) -> bool:
        """Update correlation clusters if needed."""
        # Update price history
        self.update_price_history(symbol_prices, candle_idx)
        
        # Check if update is needed
        candles_since_update = candle_idx - self.last_update_candle
        if not force_update and candles_since_update < self.config.update_frequency:
            return False
        
        symbols = list(symbol_prices.keys())
        if len(symbols) < self.config.min_cluster_size:
            self.logger.warning(f"Too few symbols ({len(symbols)}) for clustering")
            return False
        
        # Calculate correlations
        correlation_matrix = self.calculate_rolling_correlations(symbols)
        if correlation_matrix.empty:
            self.logger.warning("Failed to calculate correlation matrix")
            return False
        
        # Detect clusters using DBSCAN (primary) or K-means (fallback)
        new_clusters = self.detect_clusters_dbscan(correlation_matrix)
        if not new_clusters:
            self.logger.info("DBSCAN failed, using K-means fallback")
            new_clusters = self.detect_clusters_kmeans(correlation_matrix)
        
        if not new_clusters:
            self.logger.warning("No valid clusters detected")
            return False
        
        # Update cluster information
        old_clusters = dict(self.clusters)  # Backup
        self.clusters.clear()
        self.symbol_to_cluster.clear()
        
        for i, cluster_symbols in enumerate(new_clusters):
            avg_correlation, representative = self.calculate_cluster_stats(
                cluster_symbols, correlation_matrix
            )
            
            stability_score = self.calculate_stability_score(cluster_symbols, i)
            
            cluster_info = ClusterInfo(
                cluster_id=i,
                symbols=cluster_symbols,
                avg_correlation=avg_correlation,
                stability_score=stability_score,
                last_updated=candle_idx,
                representative_symbol=representative
            )
            
            self.clusters[i] = cluster_info
            
            # Update symbol mapping
            for symbol in cluster_symbols:
                self.symbol_to_cluster[symbol] = i
        
        self.last_update_candle = candle_idx
        
        self.logger.info(f"Updated {len(self.clusters)} clusters with avg stability "
                        f"{np.mean([c.stability_score for c in self.clusters.values()]):.2f}")
        
        return True
    
    def get_cluster_for_symbol(self, symbol: str) -> Optional[int]:
        """Get cluster ID for a symbol."""
        return self.symbol_to_cluster.get(symbol)
    
    def get_cluster_symbols(self, cluster_id: int) -> Set[str]:
        """Get all symbols in a cluster."""
        if cluster_id in self.clusters:
            return self.clusters[cluster_id].symbols
        return set()
    
    def get_correlated_symbols(self, symbol: str, max_symbols: int = 5) -> List[str]:
        """Get symbols correlated with the given symbol."""
        cluster_id = self.get_cluster_for_symbol(symbol)
        if cluster_id is None:
            return []
        
        cluster_symbols = list(self.get_cluster_symbols(cluster_id))
        # Remove the symbol itself
        if symbol in cluster_symbols:
            cluster_symbols.remove(symbol)
        
        return cluster_symbols[:max_symbols]
    
    def apply_cluster_limits(self, signals: List[Dict], max_per_cluster: int = 2) -> List[Dict]:
        """Apply position limits per correlation cluster."""
        if not signals:
            return signals
        
        cluster_counts = {}
        filtered_signals = []
        
        for signal in signals:
            symbol = signal.get('symbol', '')
            cluster_id = self.get_cluster_for_symbol(symbol)
            
            if cluster_id is None:
                # Symbol not in any cluster - allow it
                filtered_signals.append(signal)
                continue
            
            current_count = cluster_counts.get(cluster_id, 0)
            
            if current_count < max_per_cluster:
                filtered_signals.append(signal)
                cluster_counts[cluster_id] = current_count + 1
            else:
                self.logger.info(f"Filtered {symbol} due to cluster {cluster_id} limit")
        
        return filtered_signals
    
    def get_cluster_summary(self) -> str:
        """Get summary of current clustering state."""
        if not self.clusters:
            return "No clusters detected"
        
        summary = f"Dynamic Correlation Clusters ({len(self.clusters)} clusters):\n"
        
        for cluster_id, cluster in self.clusters.items():
            symbols_str = ", ".join(sorted(list(cluster.symbols)))
            summary += f"Cluster {cluster_id}: {len(cluster.symbols)} symbols "
            summary += f"(corr={cluster.avg_correlation:.2f}, stability={cluster.stability_score:.2f})\n"
            summary += f"  Symbols: {symbols_str}\n"
            summary += f"  Representative: {cluster.representative_symbol}\n\n"
        
        return summary
    
    def export_cluster_data(self) -> Dict:
        """Export cluster data for analysis or persistence."""
        return {
            'clusters': {
                cid: {
                    'symbols': list(cluster.symbols),
                    'avg_correlation': cluster.avg_correlation,
                    'stability_score': cluster.stability_score,
                    'representative_symbol': cluster.representative_symbol,
                    'last_updated': cluster.last_updated
                }
                for cid, cluster in self.clusters.items()
            },
            'symbol_to_cluster': dict(self.symbol_to_cluster),
            'last_update_candle': self.last_update_candle
        }