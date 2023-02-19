from typing import TYPE_CHECKING
import logging

import claripy
import pyvex

from .resolver import IndirectJumpResolver
from ....code_location import CodeLocation
from ...propagator import vex_vars

if TYPE_CHECKING:
    from angr import Block

l = logging.getLogger(name=__name__)


def exists_in_replacements(replacements, block_loc, tmp_var):
    exists = False
    for rep in replacements:
        if rep == block_loc:
            exists = True
            break

    if not exists:
        return False

    exists = False
    for var in replacements[block_loc]:
        if var == tmp_var:
            exists = True
            break

    return exists


class ConstantResolver(IndirectJumpResolver):
    """
    Resolve an indirect jump by running a contant propagation on the entire function and check if the indirect jump can
    be resolved to a constant value. This resolver must be run after all other more specific resolvers.
    """

    def __init__(self, project):
        super().__init__(project, timeless=False)

    def filter(self, cfg, addr, func_addr, block, jumpkind):
        # we support both an indirect call and jump since the value can be resolved
        if jumpkind in {"Ijk_Boring", "Ijk_Call"}:
            return True

        return False

    def resolve(self, cfg, addr: int, func_addr: int, block: "Block", jumpkind: str):
        """
        This function does the actual resolve. Our process is easy:
        Propagate all values inside the function specified, then extract
        the tmp_var used for the indirect jump from the basic block.
        Use the tmp var to locate the constant value stored in the replacements.
        If not present, returns False tuple.

        :param cfg:         CFG with specified function
        :param addr:        Address of indirect jump
        :param func_addr:   Address of function of indirect jump
        :param block:       Block of indirect jump (Block object)
        :param jumpkind:    VEX jumpkind (Ijk_Boring or Ijk_Call)
        :return:            Bool tuple with replacement address
        """
        vex_block = block.vex
        if isinstance(vex_block.next, pyvex.expr.RdTmp):
            # check if function is completed
            func = cfg.functions[func_addr]
            prop = self.project.analyses.Propagator(
                func=func,
                only_consts=True,
                do_binops=True,
                vex_cross_insn_opt=False,
                completed_funcs=cfg._completed_functions,
            )

            replacements = prop.replacements
            if replacements:
                block_loc = CodeLocation(block.addr, None)
                tmp_var = vex_vars.VEXTmp(vex_block.next.tmp)

                if exists_in_replacements(replacements, block_loc, tmp_var):
                    resolved_tmp = replacements[block_loc][tmp_var]

                    if (
                        isinstance(resolved_tmp, claripy.ast.Base)
                        and resolved_tmp.op == "BVV"
                        and self._is_target_valid(cfg, resolved_tmp.args[0])
                    ):
                        return True, [resolved_tmp.args[0]]

        return False, []
