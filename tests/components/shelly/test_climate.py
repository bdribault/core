"""Tests for Shelly climate platform."""
from unittest.mock import AsyncMock, PropertyMock

from aioshelly.exceptions import DeviceConnectionError, InvalidAuthError
import pytest

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    DOMAIN as CLIMATE_DOMAIN,
    PRESET_NONE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACMode,
)
from homeassistant.components.shelly.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, STATE_UNAVAILABLE
from homeassistant.core import State
from homeassistant.exceptions import HomeAssistantError

from . import init_integration, register_device, register_entity

from tests.common import mock_restore_cache

SENSOR_BLOCK_ID = 3
DEVICE_BLOCK_ID = 4
ENTITY_ID = f"{CLIMATE_DOMAIN}.test_name"


async def test_climate_hvac_mode(hass, mock_block_device, monkeypatch):
    """Test climate hvac mode service."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    # Test initial hvac mode - off
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF

    # Test set hvac mode heat
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )
    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": 20.0}
    )

    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 20.0)
    mock_block_device.mock_update()
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.HEAT

    # Test set hvac mode off
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.OFF},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": "4"}
    )

    monkeypatch.setattr(mock_block_device.blocks[SENSOR_BLOCK_ID], "targetTemp", 4.0)
    mock_block_device.mock_update()
    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF

    # Test unavailable on error
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 1)
    mock_block_device.mock_update()
    state = hass.states.get(ENTITY_ID)
    assert state.state == STATE_UNAVAILABLE


async def test_climate_set_temperature(hass, mock_block_device, monkeypatch):
    """Test climate set temperature service."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_TEMPERATURE] == 4

    # Test set temperature without target temperature
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {
            ATTR_ENTITY_ID: ENTITY_ID,
            ATTR_TARGET_TEMP_LOW: 20,
            ATTR_TARGET_TEMP_HIGH: 30,
        },
        blocking=True,
    )
    mock_block_device.http_request.assert_not_called()

    # Test set temperature
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_TEMPERATURE: 23},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"target_t_enabled": 1, "target_t": "23.0"}
    )


async def test_climate_set_preset_mode(hass, mock_block_device, monkeypatch):
    """Test climate set preset mode service."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "mode", None)
    await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_NONE

    # Test set Profile2
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "Profile2"},
        blocking=True,
    )

    mock_block_device.http_request.assert_called_once_with(
        "get", "thermostat/0", {"schedule": 1, "schedule_profile": "2"}
    )

    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "mode", 2)
    mock_block_device.mock_update()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_PRESET_MODE] == "Profile2"

    # Set preset to none
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: PRESET_NONE},
        blocking=True,
    )

    assert len(mock_block_device.http_request.mock_calls) == 2
    mock_block_device.http_request.assert_called_with(
        "get", "thermostat/0", {"schedule": 0}
    )

    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "mode", 0)
    mock_block_device.mock_update()

    state = hass.states.get(ENTITY_ID)
    assert state.attributes[ATTR_PRESET_MODE] == PRESET_NONE


async def test_block_restored_climate(hass, mock_block_device, device_reg, monkeypatch):
    """Test block restored climate."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    register_device(device_reg, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
    )
    mock_restore_cache(hass, [State(entity_id, HVACMode.HEAT)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == HVACMode.HEAT

    # Partial update, should not change state
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == HVACMode.HEAT

    # Make device online
    monkeypatch.setattr(mock_block_device, "initialized", True)
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == HVACMode.OFF


async def test_block_restored_climate_unavailable(
    hass, mock_block_device, device_reg, monkeypatch
):
    """Test block restored climate unavailable state."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    register_device(device_reg, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
    )
    mock_restore_cache(hass, [State(entity_id, STATE_UNAVAILABLE)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == HVACMode.OFF


async def test_block_restored_climate_set_preset_before_online(
    hass, mock_block_device, device_reg, monkeypatch
):
    """Test block restored climate set preset before device is online."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    register_device(device_reg, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
    )
    mock_restore_cache(hass, [State(entity_id, HVACMode.HEAT)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == HVACMode.HEAT

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_PRESET_MODE: "Profile1"},
        blocking=True,
    )

    mock_block_device.http_request.assert_not_called()


async def test_block_set_mode_connection_error(hass, mock_block_device, monkeypatch):
    """Test block device set mode connection error."""
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.setattr(
        mock_block_device,
        "http_request",
        AsyncMock(side_effect=DeviceConnectionError),
    )
    await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    with pytest.raises(HomeAssistantError):
        await hass.services.async_call(
            CLIMATE_DOMAIN,
            SERVICE_SET_HVAC_MODE,
            {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
            blocking=True,
        )


async def test_block_set_mode_auth_error(hass, mock_block_device, monkeypatch):
    """Test block device set mode authentication error."""
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    monkeypatch.setattr(
        mock_block_device,
        "http_request",
        AsyncMock(side_effect=InvalidAuthError),
    )
    entry = await init_integration(hass, 1, sleep_period=1000)

    # Make device online
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: ENTITY_ID, ATTR_HVAC_MODE: HVACMode.HEAT},
        blocking=True,
    )

    assert entry.state == ConfigEntryState.LOADED

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1

    flow = flows[0]
    assert flow.get("step_id") == "reauth_confirm"
    assert flow.get("handler") == DOMAIN

    assert "context" in flow
    assert flow["context"].get("source") == SOURCE_REAUTH
    assert flow["context"].get("entry_id") == entry.entry_id


async def test_block_restored_climate_auth_error(
    hass, mock_block_device, device_reg, monkeypatch
):
    """Test block restored climate with authentication error during init."""
    monkeypatch.delattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "targetTemp")
    monkeypatch.setattr(mock_block_device.blocks[DEVICE_BLOCK_ID], "valveError", 0)
    entry = await init_integration(hass, 1, sleep_period=1000, skip_setup=True)
    register_device(device_reg, entry)
    entity_id = register_entity(
        hass,
        CLIMATE_DOMAIN,
        "test_name",
        "sensor_0",
        entry,
    )
    mock_restore_cache(hass, [State(entity_id, HVACMode.HEAT)])

    monkeypatch.setattr(mock_block_device, "initialized", False)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED

    # Make device online with auth error
    monkeypatch.setattr(mock_block_device, "initialized", True)
    type(mock_block_device).settings = PropertyMock(
        return_value={}, side_effect=InvalidAuthError
    )
    mock_block_device.mock_update()
    await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.LOADED

    flows = hass.config_entries.flow.async_progress()
    assert len(flows) == 1

    flow = flows[0]
    assert flow.get("step_id") == "reauth_confirm"
    assert flow.get("handler") == DOMAIN

    assert "context" in flow
    assert flow["context"].get("source") == SOURCE_REAUTH
    assert flow["context"].get("entry_id") == entry.entry_id
