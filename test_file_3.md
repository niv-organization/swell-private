# Test File 3

This is a test file with substantial content to ensure the PR description
generation takes longer than 2 seconds.

## Purpose
This file tests the abort functionality for PR descriptions when processing
takes too long.

## Implementation Details

### Function 3
```python
def test_function_3():
    """
    Test function 3 with multiple lines of code
    to make the PR have substantial changes.
    """
    result = []
    for j in range(100):
        if j % 2 == 0:
            result.append(j * 2)
        else:
            result.append(j * 3)
    
    # Process results
    processed = [x for x in result if x > 50]
    
    # Return final result
    return {
        'data': processed,
        'count': len(processed),
        'timestamp': datetime.now()
    }
```

### Additional Context
This change is part of testing the LINBEE-20347 feature which handles
aborting PR description generation when it exceeds time limits.

The implementation includes:
- Timeout handling
- Graceful degradation
- Error reporting
- Logging improvements

## Testing
- Unit tests added
- Integration tests updated
- Performance benchmarks included
