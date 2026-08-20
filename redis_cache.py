from redis.asyncio import Redis
from typing import Any, Optional, Callable, TypeVar
import asyncio
import json

T = TypeVar('T');

class CacheService:
    def __init__(self, redis: Redis, prefix: str = "cache"):
        self.redis = redis;
        self.prefix = prefix;
    
    def _key(self, name: str) -> str:
        return f"{self.prefix}:{name}";
    
    async def get(self, key: str) -> Optional[Any]:
        data = await self.redis.get(self._key(key));
        if data:
            return json.loads(data);
        return None;
    
    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        await self.redis.setex(
            self._key(key),
            ttl,
            json.dumps(value, default=str)
        );
    
    async def delete(self, key: str) -> None:
        await self.redis.delete(self._key(key));
    
    async def exists(self, key: str) -> bool:
        return await self.redis.exists(self._key(key)) > 0;
    
    async def remember(self, key: str, ttl: int, callback: Callable[[], T]) -> T:
        cached = await self.get(key);
        if cached is not None:
            return cached;
        
        result = await callback() if asyncio.iscoroutinefunction(callback) else callback();
        await self.set(key, result, ttl);
        return result;
    
    async def flush_pattern(self, pattern: str) -> int:
        cursor = 0;
        deleted = 0;
        while True:
            cursor, keys = await self.redis.scan(
                cursor,
                match=self._key(pattern),
                count=100
            );
            if keys:
                deleted += await self.redis.delete(*keys);
            if cursor == 0:
                break;
        return deleted;