"""
Dynamic Cache TTL Manager for Multi-Timeframe Trading Data
Implements timeframe-aware caching with dynamic TTL values.
"""

import logging
import time
from dataclasses import dataclass
from typing import Dict, Any, Optional, Union
from abc import ABC, abstractmethod

logger = logging.getLogger(__name__)

@dataclass
class CacheConfig:
    """Cache configuration for different timeframes."""
    base_ttl_seconds: int  # Base TTL for this timeframe
    max_ttl_seconds: int   # Maximum TTL allowed
    min_ttl_seconds: int   # Minimum TTL allowed
    volatility_factor: float  # Multiplier based on volatility
    data_type_factor: float   # Different factors for different data types

class CacheInterface(ABC):
    """Abstract interface for cache implementations."""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int = None) -> None:
        """Set value in cache with TTL."""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """Clear all cache entries."""
        pass
    
    @abstractmethod
    def size(self) -> int:
        """Get cache size."""
        pass

@dataclass
class CacheEntry:
    """Cache entry with metadata."""
    value: Any
    timestamp: float
    ttl_seconds: int
    access_count: int = 0
    last_access: float = 0

class InMemoryCache(CacheInterface):
    """In-memory cache implementation."""
    
    def __init__(self, max_size: int = 1000):
        self.cache: Dict[str, CacheEntry] = {}
        self.max_size = max_size
        self.logger = logging.getLogger(__name__)
    
    def _is_expired(self, entry: CacheEntry) -> bool:
        """Check if cache entry is expired."""
        return time.time() - entry.timestamp > entry.ttl_seconds
    
    def _cleanup_expired(self) -> None:
        """Remove expired entries."""
        current_time = time.time()
        expired_keys = [
            key for key, entry in self.cache.items()
            if current_time - entry.timestamp > entry.ttl_seconds
        ]
        
        for key in expired_keys:
            del self.cache[key]
    
    def _evict_if_needed(self) -> None:
        """Evict entries if cache is full."""
        if len(self.cache) >= self.max_size:
            # Remove least recently used entries
            sorted_entries = sorted(
                self.cache.items(),
                key=lambda x: x[1].last_access or x[1].timestamp
            )
            
            # Remove oldest 10% of entries
            to_remove = max(1, len(sorted_entries) // 10)
            for i in range(to_remove):
                key = sorted_entries[i][0]
                del self.cache[key]
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache."""
        self._cleanup_expired()
        
        if key not in self.cache:
            return None
        
        entry = self.cache[key]
        if self._is_expired(entry):
            del self.cache[key]
            return None
        
        # Update access statistics
        entry.access_count += 1
        entry.last_access = time.time()
        
        return entry.value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in cache with TTL."""
        self._cleanup_expired()
        self._evict_if_needed()
        
        entry = CacheEntry(
            value=value,
            timestamp=time.time(),
            ttl_seconds=ttl_seconds,
            access_count=0,
            last_access=0
        )
        
        self.cache[key] = entry
    
    def delete(self, key: str) -> bool:
        """Delete key from cache."""
        if key in self.cache:
            del self.cache[key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
    
    def size(self) -> int:
        """Get cache size."""
        self._cleanup_expired()
        return len(self.cache)

class StreamlitCacheAdapter(CacheInterface):
    """Adapter for Streamlit session state."""
    
    def __init__(self, session_state):
        self.session_state = session_state
        self.cache_key_prefix = "_cache_"
        self.logger = logging.getLogger(__name__)
    
    def _make_key(self, key: str) -> str:
        """Make internal cache key."""
        return f"{self.cache_key_prefix}{key}"
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from session state."""
        internal_key = self._make_key(key)
        
        if internal_key not in self.session_state:
            return None
        
        entry = self.session_state[internal_key]
        if not isinstance(entry, dict) or 'value' not in entry:
            return None
        
        # Check expiry
        if time.time() - entry.get('timestamp', 0) > entry.get('ttl_seconds', 300):
            del self.session_state[internal_key]
            return None
        
        return entry['value']
    
    def set(self, key: str, value: Any, ttl_seconds: int = 300) -> None:
        """Set value in session state."""
        internal_key = self._make_key(key)
        
        entry = {
            'value': value,
            'timestamp': time.time(),
            'ttl_seconds': ttl_seconds
        }
        
        self.session_state[internal_key] = entry
    
    def delete(self, key: str) -> bool:
        """Delete key from session state."""
        internal_key = self._make_key(key)
        if internal_key in self.session_state:
            del self.session_state[internal_key]
            return True
        return False
    
    def clear(self) -> None:
        """Clear all cache entries from session state."""
        keys_to_delete = [
            key for key in self.session_state.keys()
            if key.startswith(self.cache_key_prefix)
        ]
        
        for key in keys_to_delete:
            del self.session_state[key]
    
    def size(self) -> int:
        """Get cache size."""
        return len([
            key for key in self.session_state.keys()
            if key.startswith(self.cache_key_prefix)
        ])

class DynamicCacheManager:
    """Manages caching with dynamic TTL based on timeframes and market conditions."""
    
    def __init__(self, cache_impl: CacheInterface = None):
        self.cache = cache_impl or InMemoryCache()
        self.logger = logging.getLogger(__name__)
        
        # Timeframe-specific cache configurations
        self.timeframe_configs = {
            '1m': CacheConfig(
                base_ttl_seconds=20,    # Very short for 1m data
                max_ttl_seconds=30,
                min_ttl_seconds=10,
                volatility_factor=1.5,
                data_type_factor=1.0
            ),
            '5m': CacheConfig(
                base_ttl_seconds=60,    # Short for 5m data
                max_ttl_seconds=90,
                min_ttl_seconds=30,
                volatility_factor=1.3,
                data_type_factor=1.0
            ),
            '15m': CacheConfig(
                base_ttl_seconds=120,   # Medium for 15m data
                max_ttl_seconds=180,
                min_ttl_seconds=60,
                volatility_factor=1.2,
                data_type_factor=1.0
            ),
            '1h': CacheConfig(
                base_ttl_seconds=180,   # Standard for 1h data
                max_ttl_seconds=300,
                min_ttl_seconds=120,
                volatility_factor=1.1,
                data_type_factor=1.0
            ),
            '4h': CacheConfig(
                base_ttl_seconds=300,   # Longer for 4h data
                max_ttl_seconds=600,
                min_ttl_seconds=180,
                volatility_factor=1.0,
                data_type_factor=1.0
            ),
            '1d': CacheConfig(
                base_ttl_seconds=600,   # Longest for daily data
                max_ttl_seconds=1200,
                min_ttl_seconds=300,
                volatility_factor=0.9,
                data_type_factor=1.0
            )
        }
        
        # Data type specific multipliers
        self.data_type_multipliers = {
            'market_data': 1.0,        # Base multiplier
            'orderbook': 0.5,          # Orderbook data is more volatile
            'funding_rates': 2.0,      # Funding rates change less frequently
            'open_interest': 1.5,      # OI changes relatively slowly
            'ticker': 0.8,             # Ticker data changes frequently
            'account_info': 3.0,       # Account info rarely changes
            'symbol_info': 10.0        # Symbol info very rarely changes
        }
    
    def calculate_dynamic_ttl(self, 
                            timeframe: str,
                            data_type: str = 'market_data',
                            volatility_score: float = 1.0,
                            market_activity: float = 1.0) -> int:
        """Calculate dynamic TTL based on various factors."""
        
        # Get base configuration
        config = self.timeframe_configs.get(timeframe, self.timeframe_configs['1h'])
        base_ttl = config.base_ttl_seconds
        
        # Apply data type multiplier
        data_multiplier = self.data_type_multipliers.get(data_type, 1.0)
        
        # Apply volatility adjustment (higher volatility = shorter cache)
        volatility_adjustment = 1.0 / (1.0 + volatility_score * 0.5)
        
        # Apply market activity adjustment (higher activity = shorter cache)
        activity_adjustment = 1.0 / (1.0 + market_activity * 0.3)
        
        # Calculate final TTL
        calculated_ttl = int(
            base_ttl * data_multiplier * volatility_adjustment * activity_adjustment
        )
        
        # Apply bounds
        final_ttl = max(config.min_ttl_seconds, 
                       min(config.max_ttl_seconds, calculated_ttl))
        
        self.logger.debug(f"Dynamic TTL for {timeframe}/{data_type}: "
                         f"base={base_ttl}, final={final_ttl}")
        
        return final_ttl
    
    def get_with_dynamic_ttl(self, 
                           key: str,
                           timeframe: str = '5m',
                           data_type: str = 'market_data') -> Optional[Any]:
        """Get value with dynamic TTL consideration."""
        return self.cache.get(key)
    
    def set_with_dynamic_ttl(self,
                           key: str,
                           value: Any,
                           timeframe: str = '5m',
                           data_type: str = 'market_data',
                           volatility_score: float = 1.0,
                           market_activity: float = 1.0) -> None:
        """Set value with dynamic TTL."""
        
        ttl = self.calculate_dynamic_ttl(
            timeframe=timeframe,
            data_type=data_type,
            volatility_score=volatility_score,
            market_activity=market_activity
        )
        
        self.cache.set(key, value, ttl)
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        return {
            'size': self.cache.size(),
            'timeframe_configs': {
                tf: {
                    'base_ttl': config.base_ttl_seconds,
                    'min_ttl': config.min_ttl_seconds,
                    'max_ttl': config.max_ttl_seconds
                }
                for tf, config in self.timeframe_configs.items()
            }
        }
    
    def clear_cache(self) -> None:
        """Clear all cache entries."""
        self.cache.clear()
    
    def delete_key(self, key: str) -> bool:
        """Delete specific key from cache."""
        return self.cache.delete(key)

# Global cache manager instance (can be overridden)
_global_cache_manager: Optional[DynamicCacheManager] = None

def get_cache_manager() -> DynamicCacheManager:
    """Get global cache manager instance."""
    global _global_cache_manager
    if _global_cache_manager is None:
        _global_cache_manager = DynamicCacheManager()
    return _global_cache_manager

def set_cache_manager(cache_manager: DynamicCacheManager) -> None:
    """Set global cache manager instance."""
    global _global_cache_manager
    _global_cache_manager = cache_manager