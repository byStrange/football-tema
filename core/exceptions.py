class DomainException(Exception):
    """Base exception for domain errors."""
    pass


class GameNotFound(DomainException):
    pass


class PlayerNotFound(DomainException):
    pass


class AlreadyJoined(DomainException):
    pass


class NotAuthorized(DomainException):
    pass


class GameFull(DomainException):
    pass


class PaymentNotFound(DomainException):
    pass


class InvalidStateTransition(DomainException):
    pass


class DuplicateAction(DomainException):
    pass
