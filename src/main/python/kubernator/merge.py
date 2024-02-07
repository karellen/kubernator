# -*- coding: utf-8 -*-
#
#   Copyright 2020 Express Systems USA, Inc
#   Copyright 2024 Karellen, Inc.
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.
#
from copy import deepcopy
from kubernator.api import jp
from jsonpath_ng.jsonpath import Index, Child


# https://github.com/kubernetes/community/blob/master/contributors/devel/sig-api-machinery/strategic-merge-patch.md

def extract_merge_instructions(manifest, resource):
    normalized_manifest = deepcopy(manifest)
    change_instrs = jp('$..`match(/\\\\$patch|\\\\$deleteFromPrimitiveList\\/.*/)`').find(manifest)

    instructions = []
    for change_instr in change_instrs:
        field = change_instr.path.fields[0]
        context = change_instr.context.value

        list_of_maps = False
        search_key = None
        change_path = change_instr.full_path.left
        if isinstance(change_path, Child) and isinstance(change_path.right, Index):
            list_of_maps = True
            index = change_path.right.index
            change_path = change_path.left
            clean_manifest_result: list = change_path.find(normalized_manifest)[0].value
            search_key = context.copy()
            del search_key[field]
            del clean_manifest_result[index]
        else:
            clean_manifest_result = change_path.find(normalized_manifest)[0]
            clean_manifest_result_context = clean_manifest_result.value
            del clean_manifest_result_context[field]

        instruction_value = context[field]
        if field == "$patch":
            if instruction_value in ("replace", "delete"):
                instructions.append(("patch", instruction_value,
                                     change_path, list_of_maps, search_key))
            else:
                raise ValueError("Invalid $patch instruction %r in resource %s at %s" %
                                 (instruction_value,
                                  resource,
                                  change_path))
        elif field.startswith("$deleteFromPrimitiveList/"):
            instructions.append(("delete-from-list", instruction_value, field[25:],
                                 change_path))

    return instructions, normalized_manifest


def apply_merge_instructions(merge_instrs, source_manifest, target_manifest, logger, resource):
    for merge_instr in merge_instrs:
        if merge_instr[0] == "patch":
            op, op_type, change_path, list_of_maps, search_key = merge_instr
        else:
            op, delete_list, field_name, change_path = merge_instr

        if op == "patch":
            source_obj = change_path.find(source_manifest)[0].value
            merged_obj = change_path.find(target_manifest)[0].value
            if op_type == "delete":
                if list_of_maps:
                    logger.trace("Deleting locally in resource %s: %s from %s at %s",
                                 resource,
                                 search_key,
                                 merged_obj,
                                 change_path)
                    del_idxs = []
                    for idx, obj in enumerate(merged_obj):
                        for k, v in search_key.items():
                            if k in obj:
                                if v is not None and obj[k] == v:
                                    del_idxs.append(idx)

                    for idx in del_idxs:
                        del merged_obj[idx]
                else:
                    logger.trace("Deleting locally in resource %s: %s at %s",
                                 resource,
                                 merged_obj,
                                 change_path)
                    merged_datum = change_path.find(target_manifest)[0]
                    merged_datum.context.value[merged_datum.path.fields[0]] = None
            elif op_type == "replace":
                logger.trace("Replacing locally in resource %s: %s with %s at %s",
                             resource,
                             merged_obj, source_obj,
                             change_path)
                merged_obj.clear()
                if list_of_maps:
                    merged_obj.extend(source_obj)
                else:
                    merged_obj.update(source_obj)
            else:
                raise ValueError("Invalid $patch instruction %s found at %s in resource %s",
                                 op_type, change_path, resource)

        elif op == "delete-from-list":
            merged_list: list = change_path.find(target_manifest)[0].value[field_name]
            if not isinstance(merged_list, list):
                raise ValueError("Not a list in resource %s: %s in %r at %s" %
                                 (resource, merged_list, field_name, change_path))
            logger.trace("Deleting from list locally in resource %s: %s from %s in %r at %s",
                         resource, delete_list, merged_list, field_name, change_path)
            for v in delete_list:
                try:
                    merged_list.remove(v)
                except ValueError:
                    logger.warning("No value %s to delete from list %s in %r at %s in resource %s",
                                   v, merged_list, field_name, change_path, resource)
        else:
            raise RuntimeError("should never reach here")
