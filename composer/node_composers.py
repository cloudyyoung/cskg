from abc import ABC, abstractmethod
from typing import Any, Iterable


class AbstractNodeComposer(ABC):
    def __init__(self, included_fields: list[str] = None):
        self.included_fields = included_fields or []

    @abstractmethod
    def get_cypher(self, entity: dict[str, Any]):
        ...


class EntityComposer(AbstractNodeComposer):
    def __init__(
        self, entity_label: str | Iterable[str], included_fields: list[str] = None
    ):
        super().__init__(included_fields)
        self.entity_type = ":".join(
            map(lambda x: x.capitalize(), ensure_list_of_strings(entity_label))
        )

    def get_cypher(self, entity: dict[str, Any]):
        entity_type = self.entity_type

        included_fields_dict = _included_fields_dict(entity, self.included_fields)
        entity_properties = [
            f"{key}: '{value}'" for key, value in included_fields_dict.items()
        ]
        entity_properties_neo = ", ".join(entity_properties)

        return f"""
            CREATE (:{entity_type} {{ {entity_properties_neo} }}) 
        """


def _included_fields_dict(dict: dict[str, Any], fields: list[str]):
    return {key: dict.get(key) for key in fields if key in dict}


class RelationshipComposer(AbstractNodeComposer):
    Field = tuple[str, str]
    """
    A tuple of (name: str, type: str).
    """

    def __init__(
        self,
        relation_label: str,
        from_field: Field,
        to_field: Field,
        included_fields: list[str] = None,
    ):
        super().__init__(included_fields)
        self.relation_type = relation_label.upper()
        self.from_field = from_field
        self.to_field = to_field

    def get_cypher(self, relationship: dict[str, Any]):
        relation_type = self.relation_type

        field_a_name, field_a_type = self.from_field
        field_b_name, field_b_type = self.to_field

        field_a_value = relationship.get(field_a_name)
        field_b_value = relationship.get(field_b_name)
        field_a_type_neo = field_a_type.capitalize()
        field_b_type_neo = field_b_type.capitalize()

        return f"""
            MATCH (a:{field_a_type_neo} {{qualified_name: "{field_a_value}"}}), (b:{field_b_type_neo} {{qualified_name: "{field_b_value}"}})
            CREATE (a)-[:{relation_type} {{}}]->(b)
        """


NodeComposer = EntityComposer | RelationshipComposer


def ensure_list_of_strings(variable):
    if isinstance(variable, str):
        return [variable]
    elif isinstance(variable, Iterable):
        return variable
    else:
        raise ValueError("Variable must be a string or a list of strings")
