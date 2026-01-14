"""Tests for result.py - Ok/Err result types."""

import pytest
from cadence.result import Ok, Err, ok, err, Result


class TestOk:
    """Tests for Ok result type."""

    def test_ok_is_ok(self):
        """Test Ok.is_ok returns True."""
        result = Ok(42)
        assert result.is_ok() is True

    def test_ok_is_err(self):
        """Test Ok.is_err returns False."""
        result = Ok(42)
        assert result.is_err() is False

    def test_ok_unwrap(self):
        """Test Ok.unwrap returns the value."""
        result = Ok("hello")
        assert result.unwrap() == "hello"

    def test_ok_unwrap_or(self):
        """Test Ok.unwrap_or returns the value, not default."""
        result = Ok(100)
        assert result.unwrap_or(0) == 100

    def test_ok_map(self):
        """Test Ok.map transforms the value."""
        result = Ok(5)
        mapped = result.map(lambda x: x * 2)
        assert isinstance(mapped, Ok)
        assert mapped.unwrap() == 10

    def test_ok_with_none_value(self):
        """Test Ok can hold None as a valid value."""
        result = Ok(None)
        assert result.is_ok() is True
        assert result.unwrap() is None

    def test_ok_with_complex_value(self):
        """Test Ok with complex nested values."""
        data = {"users": [{"name": "Alice"}, {"name": "Bob"}]}
        result = Ok(data)
        assert result.unwrap() == data


class TestErr:
    """Tests for Err result type."""

    def test_err_is_ok(self):
        """Test Err.is_ok returns False."""
        result = Err(ValueError("error"))
        assert result.is_ok() is False

    def test_err_is_err(self):
        """Test Err.is_err returns True."""
        result = Err(ValueError("error"))
        assert result.is_err() is True

    def test_err_unwrap_raises(self):
        """Test Err.unwrap raises the error."""
        error = ValueError("something went wrong")
        result = Err(error)
        with pytest.raises(ValueError, match="something went wrong"):
            result.unwrap()

    def test_err_unwrap_or(self):
        """Test Err.unwrap_or returns the default."""
        result = Err(ValueError("error"))
        assert result.unwrap_or("default") == "default"

    def test_err_map(self):
        """Test Err.map doesn't transform and returns self."""
        error = ValueError("error")
        result = Err(error)
        mapped = result.map(lambda x: x * 2)
        assert isinstance(mapped, Err)
        assert mapped.error is error


class TestHelperFunctions:
    """Tests for ok() and err() helper functions."""

    def test_ok_function(self):
        """Test ok() creates an Ok result."""
        result = ok(42)
        assert isinstance(result, Ok)
        assert result.value == 42

    def test_err_function(self):
        """Test err() creates an Err result."""
        error = RuntimeError("runtime error")
        result = err(error)
        assert isinstance(result, Err)
        assert result.error is error


class TestResultTypeAlias:
    """Tests for Result type usage patterns."""

    def test_result_with_ok(self):
        """Test Result type can be Ok."""

        def divide(a: int, b: int) -> Result[int, ZeroDivisionError]:
            if b == 0:
                return Err(ZeroDivisionError("division by zero"))
            return Ok(a // b)

        result = divide(10, 2)
        assert result.is_ok()
        assert result.unwrap() == 5

    def test_result_with_err(self):
        """Test Result type can be Err."""

        def divide(a: int, b: int) -> Result[int, ZeroDivisionError]:
            if b == 0:
                return Err(ZeroDivisionError("division by zero"))
            return Ok(a // b)

        result = divide(10, 0)
        assert result.is_err()
        with pytest.raises(ZeroDivisionError):
            result.unwrap()
