from __future__ import annotations

from decimal import Decimal, ROUND_UP

from db.models import Game


class PaymentCalculator:
    @staticmethod
    def calculate_per_player(game: Game, participant_count: int) -> Decimal:
        if game.cost_per_player is not None:
            return game.cost_per_player

        if game.total_cost is not None:
            if participant_count <= 0:
                raise ValueError("Participant count must be greater than zero.")
            per_player = game.total_cost / participant_count
            return per_player.quantize(Decimal("0.01"), rounding=ROUND_UP)

        raise ValueError("Game must have either total_cost or cost_per_player set.")
