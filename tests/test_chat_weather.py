"""Offline tests for chat persistence and partial weather responses."""
from __future__ import annotations

import sqlite3
import unittest
from unittest.mock import AsyncMock, patch

from app import db, main
from app.tools import weather
from tests.base import AsyncHomeTestCase


class ChatWeatherTests(AsyncHomeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.db_path = self.use_temp_db()

    async def test_chat_persists_complete_exchange_and_recalls_it(self):
        with patch.object(main.llm, "chat", new_callable=AsyncMock) as llm_chat:
            llm_chat.side_effect = ["First reply", "Second reply"]
            self.assertEqual((await main.chat(main.ChatRequest(text="First"))).reply, "First reply")
            self.assertEqual((await main.chat(main.ChatRequest(text="Second"))).reply, "Second reply")

        self.assertEqual(
            db.history_recent(4),
            [
                {"role": "user", "content": "First"},
                {"role": "assistant", "content": "First reply"},
                {"role": "user", "content": "Second"},
                {"role": "assistant", "content": "Second reply"},
            ],
        )
        second_messages = llm_chat.await_args_list[1].args[0]
        self.assertEqual([m["content"] for m in second_messages[-3:]], ["First", "First reply", "Second"])
        with sqlite3.connect(self.db_path) as conn:
            self.assertEqual(conn.execute("PRAGMA journal_mode").fetchone()[0], "wal")

    async def test_forecast_uses_only_available_dates_and_optional_values(self):
        payload = {
            "daily": {
                "time": ["2026-09-27", "2026-09-28"],
                "temperature_2m_max": [16],
                "weather_code": [0, 61],
            }
        }
        with patch.object(weather, "_fetch", new_callable=AsyncMock, return_value=payload):
            forecast = await weather.weather_forecast(7)
        self.assertEqual(len(forecast["days"]), 2)
        self.assertEqual(forecast["days"][0]["max"], 16)
        self.assertIsNone(forecast["days"][1]["max"])
        self.assertIsNone(forecast["days"][0]["min"])
        self.assertEqual(forecast["days"][1]["condition"], "light rain")


if __name__ == "__main__":
    unittest.main()
