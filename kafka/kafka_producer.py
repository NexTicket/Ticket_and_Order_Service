import json
import os
import time
from typing import Dict, Any, Optional, Union
from confluent_kafka import Producer, KafkaException
import logging
from functools import wraps

# Configure logging with more detailed format
log_level = os.getenv('KAFKA_LOG_LEVEL', 'INFO')
logging.basicConfig(
    level=getattr(logging, log_level),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# Default Kafka Producer Configuration
DEFAULT_CONFIG = {
    'bootstrap.servers': os.getenv('KAFKA_BOOTSTRAP_SERVERS', 'kafka:9092'),
    'client.id': os.getenv('KAFKA_CLIENT_ID', 'ticket-order-service'),
    'acks': os.getenv('KAFKA_ACKS', 'all'),                     # Wait for all replicas to acknowledge
    'retries': int(os.getenv('KAFKA_RETRIES', '3')),           # Retry on transient errors
    'retry.backoff.ms': int(os.getenv('KAFKA_RETRY_BACKOFF_MS', '200')),  # Time between retries
    'linger.ms': int(os.getenv('KAFKA_LINGER_MS', '10')),      # Small delay to batch messages
    'batch.size': int(os.getenv('KAFKA_BATCH_SIZE', '16384')), # 16KB batches for efficiency
    'compression.type': os.getenv('KAFKA_COMPRESSION_TYPE', 'snappy'),  # Compress messages
    'max.in.flight.requests.per.connection': int(os.getenv('KAFKA_MAX_IN_FLIGHT_REQUESTS', '5')),  # Controls order guarantee
    'enable.idempotence': os.getenv('KAFKA_ENABLE_IDEMPOTENCE', 'true').lower() == 'true',  # Exactly-once semantics
    'socket.keepalive.enable': os.getenv('KAFKA_SOCKET_KEEPALIVE_ENABLE', 'true').lower() == 'true',  # Keep connection alive
}

# Topics configuration - centralizing for easier maintenance
TOPICS = {
    "notifications": os.getenv('KAFKA_NOTIFICATIONS_TOPIC', 'ticket_notifications'),
    "order_events": os.getenv('KAFKA_ORDER_EVENTS_TOPIC', 'order_events'),
    "ticket_events": os.getenv('KAFKA_TICKET_EVENTS_TOPIC', 'ticket_events'),
}

# Producer instance - lazy initialization
_producer = None

def get_producer() -> Producer:
    """
    Get or create the Kafka producer instance.
    Uses lazy initialization for better resource management.
    """
    global _producer
    if _producer is None:
        _producer = Producer(DEFAULT_CONFIG)
        logger.info(f"Kafka producer initialized with config: {DEFAULT_CONFIG}")
    return _producer

def with_retry(max_retries=3, retry_delay=1):
    """
    Decorator for retrying Kafka operations on failure.
    
    Args:
        max_retries: Maximum number of retry attempts
        retry_delay: Base delay between retries (will be increased exponentially)
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            last_exception = None
            
            while attempts < max_retries:
                try:
                    return func(*args, **kwargs)
                except KafkaException as e:
                    last_exception = e
                    attempts += 1
                    wait_time = retry_delay * (2 ** (attempts - 1))  # Exponential backoff
                    logger.warning(f"Kafka operation failed, retrying in {wait_time}s. Attempt {attempts}/{max_retries}. Error: {e}")
                    time.sleep(wait_time)
            
            # If we get here, all retries failed
            logger.error(f"All {max_retries} retry attempts failed for Kafka operation: {last_exception}")
            raise last_exception
            
        return wrapper
    return decorator

def delivery_report(err: Optional[KafkaException], msg: Any) -> None:
    """
    Callback executed once Kafka has acknowledged the message.
    
    Args:
        err: Error that occurred during delivery (None if successful)
        msg: Message that was delivered
    """
    message_id = msg.key().decode('utf-8') if msg.key() else 'N/A'
    
    if err is not None:
        logger.error(f"Message delivery failed for ID {message_id}: {err}")
    else:
        # Log at debug level to avoid excessive logging in production
        logger.debug(f"Message delivered: topic={msg.topic()}, partition={msg.partition()}, offset={msg.offset()}, id={message_id}")

@with_retry(max_retries=3)
def send_notification_message(qr_data: str, firebase_uid: str) -> bool:
    """
    Sends a notification message to the Kafka topic.
    
    Args:
        qr_data: QR code data to be included in the message
        firebase_uid: Firebase user ID for targeting notification
        
    Returns:
        bool: True if message was produced successfully, False otherwise
    """
    # Input validation
    if not qr_data or not firebase_uid:
        logger.error("Invalid input: qr_data and firebase_uid must not be empty")
        return False
        
    try:
        # Generate message ID for tracking (using timestamp + user ID)
        message_id = f"{int(time.time())}-{firebase_uid}"
        
        # Create the message payload
        message_payload = {
            'qr_data': qr_data,
            'firebase_uid': firebase_uid,
            'timestamp': int(time.time()),
            'message_id': message_id,
        }
        
        # Serialize to JSON
        message_value = json.dumps(message_payload).encode('utf-8')
        
        # Use user ID as key for ordering and partition assignment
        message_key = firebase_uid.encode('utf-8')
        
        # Get topic name from centralized config
        topic = TOPICS["notifications"]
        
        # Produce the message
        producer = get_producer()
        producer.produce(
            topic=topic,
            key=message_key,
            value=message_value,
            callback=delivery_report,
            headers={
                'service': b'ticket-order-service',
                'message_type': b'notification',
            }
        )
        
        # Poll with small timeout to handle delivery reports
        producer.poll(0.1)
        
        logger.info(f"Notification message queued: {message_id} for user {firebase_uid}")
        return True
        
    except Exception as e:
        logger.error(f"Error producing message to Kafka: {e}", exc_info=True)
        # Don't flush on every error - let the producer handle retries
        return False

@with_retry(max_retries=DEFAULT_CONFIG['retries'])
def send_message(topic: str, key: str, data: Dict[str, Any], headers: Optional[Dict[str, bytes]] = None) -> bool:
    """
    Generic method to send any message to a specified Kafka topic.
    
    Args:
        topic: Kafka topic to send message to
        key: Message key for partitioning
        data: Dictionary containing the message data
        headers: Optional Kafka message headers
        
    Returns:
        bool: True if message was produced successfully, False otherwise
    """
    try:
        # Add metadata
        data['timestamp'] = int(time.time())
        data['messageId'] = f"{int(time.time())}-{key}"
        
        # Encode data and key
        value = json.dumps(data).encode('utf-8')
        key_bytes = key.encode('utf-8')
        
        # Set default headers if not provided
        if headers is None:
            headers = {'service': b'ticket-order-service'}
            
        # Get producer and send message
        producer = get_producer()
        producer.produce(
            topic=topic, 
            key=key_bytes,
            value=value, 
            headers=headers,
            callback=delivery_report
        )
        
        # Poll with small timeout to handle delivery reports
        producer.poll(0.1)
        
        logger.info(f"Message sent to {topic} with key {key}")
        return True
        
    except Exception as e:
        logger.error(f"Failed to send message to topic {topic}: {e}", exc_info=True)
        return False

def flush_producer(timeout: Optional[float] = None) -> None:
    """
    Flush all outstanding messages.
    
    Args:
        timeout: Maximum time to block waiting for flushed messages
    """
    if _producer is not None:
        logger.info("Flushing Kafka producer...")
        unflushed = _producer.flush(timeout or 10.0)
        if unflushed > 0:
            logger.warning(f"{unflushed} message(s) remain unflushed after timeout")
        else:
            logger.info("All messages flushed successfully")

def close() -> None:
    """
    Clean shutdown of the Kafka producer.
    Should be called when the application is shutting down.
    """
    if _producer is not None:
        # Flush remaining messages with 5s timeout
        flush_producer(5.0)
        logger.info("Kafka producer closed")