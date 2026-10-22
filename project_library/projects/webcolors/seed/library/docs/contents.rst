.. module:: webcolors

.. _contents:


API reference
=============

The contents of the ``webcolors`` module fall into five categories:

1. A set of (optional) data types for representing color values.

2. Constants for several purposes.

3. Normalization functions which sanitize input in various formats prior to
   conversion or output.

4. Conversion functions between each method of specifying colors.

5. Implementations of the color parsing and serialization algorithms in HTML5.

See :ref:`the documentation regarding conventions <conventions>` for
information regarding the types and representation of various color formats in
``webcolors``.

All conversion functions which involve color names take an optional argument to
determine the specification from which to draw color names. See :ref:`the set
of specification identifiers <spec-constants>` for valid values.

All conversion functions, when faced with identifiably invalid hexadecimal
color values, or with a request to name a color which has no name in the
requested specification, or with an invalid specification identifier, will
raise :exc:`ValueError`.

.. admonition:: **Imports and submodules**

   The public, supported API of ``webcolors`` is exported from its top-level
   module, ``webcolors``. Although the codebase is internally organized into
   several submodules for easier maintenance, the existence, names, and
   organization of these submodules is *not* part of ``webcolors``' supported
   API and cannot be relied upon.

   For example: although :func:`normalize_hex` is actually implemented in a
   submodule named ``webcolors._normalization``, it must always be referred to
   as ``webcolors.normalize_hex``, **never** as
   ``webcolors._normalization.normalize_hex``.


Data types
----------

Integer and percentage ``rgb()`` triplets, and HTML5 simple colors, can be
passed to functions in ``webcolors`` as plain 3-:class:`tuple` of the
appropriate data type. But the following :class:`~typing.NamedTuple` instances
are also provided to represent these types more richly, and functions in
``webcolors`` which return triplets or simple colors will return instances of
these:

.. autoclass:: IntegerRGB
.. autoclass:: PercentRGB
.. autoclass:: HTML5SimpleColor

Additionally, to aid in type annotations, the following type aliases are
defined, and used throughout this module:

.. autodata:: IntTuple
.. autodata:: PercentTuple


.. _spec-constants:

Constants
---------

The following constants are available for indicating the specification from
which to draw color name choices, in functions which can work with multiple
specifications.

.. data:: CSS2

   Represents the CSS2 specification. Value is ``"css2"``.

.. data:: CSS21

   Represents the CSS2.1 specification. Value is ``"css21"``.

.. data:: CSS3

   Represents the CSS3 specification. Value is ``"css3"``.

.. data:: HTML4

   Represents the HTML 4 specification. Value is ``"html4"``.


Informative functions
---------------------

.. autofunction:: names


Normalization functions
-----------------------

.. autofunction:: normalize_hex
.. autofunction:: normalize_integer_triplet
.. autofunction:: normalize_percent_triplet


Conversions from color names to other formats
---------------------------------------------

.. autofunction:: name_to_hex
.. autofunction:: name_to_rgb
.. autofunction:: name_to_rgb_percent


Conversions from hexadecimal color values to other formats
----------------------------------------------------------

.. autofunction:: hex_to_name
.. autofunction:: hex_to_rgb
.. autofunction:: hex_to_rgb_percent


Conversions from integer ``rgb()`` triplets to other formats
------------------------------------------------------------

.. autofunction:: rgb_to_name
.. autofunction:: rgb_to_hex
.. autofunction:: rgb_to_rgb_percent


Conversions from percentage ``rgb()`` triplets to other formats
---------------------------------------------------------------

.. autofunction:: rgb_percent_to_name
.. autofunction:: rgb_percent_to_hex
.. autofunction:: rgb_percent_to_rgb


.. _html5-algorithms:

HTML5 color algorithms
----------------------

.. warning:: Previously there were two competing HTML5 standards: one from
   WHATWG, and one from W3C. The WHATWG version is now the sole official HTML5
   standard, and so the functions documented below implement the HTML5 color
   algorithms as given in `section 2.3.6 of the WHATWG HTML5 standard
   <https://html.spec.whatwg.org/multipage/common-microsyntaxes.html#colours>`_.

.. autofunction:: html5_parse_simple_color
.. autofunction:: html5_serialize_simple_color
.. autofunction:: html5_parse_legacy_color
