import inspect
import logging

import click

from copernicusmarine.core_functions.deprecated_options import (
    DEPRECATED_OPTIONS,
)
from copernicusmarine.core_functions.utils import log_deprecated_message

logger = logging.getLogger("copernicusmarine")


class DeprecatedClickOption(click.Option):
    def __init__(self, *args, **kwargs):
        self.deprecated = kwargs.pop("deprecated", ())
        self.preferred = kwargs.pop("preferred", args[0][-1])
        super().__init__(*args, **kwargs)


class CustomClickOptionsCommand(click.Command):
    def make_parser(self, ctx):
        parser = super().make_parser(ctx)

        # get the parser options
        options = set(parser._short_opt.values())
        options |= set(parser._long_opt.values())

        # get name of the command
        command_name = ctx.command.name

        for option in options:

            def make_process(an_option):
                orig_process = an_option.process
                deprecated = getattr(an_option.obj, "deprecated", [])
                preferred = getattr(an_option.obj, "preferred", [])

                def process(value, state):
                    frame = inspect.currentframe()
                    try:
                        opt = frame.f_back.f_locals.get("opt")
                    finally:
                        del frame
                    old_alias = opt.replace("--", "").replace("-", "_")  # type: ignore
                    if (
                        opt in deprecated
                        or old_alias
                        in DEPRECATED_OPTIONS.deprecated_options_by_old_names
                    ):
                        alias_info = (
                            DEPRECATED_OPTIONS.deprecated_options_by_old_names[
                                old_alias
                            ]
                        )
                        if command_name in alias_info.targeted_functions:
                            log_deprecated_message(
                                opt,
                                preferred,
                                alias_info.deleted_for_v2,
                                alias_info.deprecated_for_v2,
                                alias_info.only_for_v2,
                            )
                    return orig_process(value, state)

                return process

            option.process = make_process(option)

        return parser
