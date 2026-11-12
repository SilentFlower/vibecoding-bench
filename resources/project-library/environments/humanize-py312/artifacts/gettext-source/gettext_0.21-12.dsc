-----BEGIN PGP SIGNED MESSAGE-----
Hash: SHA512

Format: 3.0 (quilt)
Source: gettext
Binary: gettext-base, gettext, gettext-el, gettext-doc, autopoint, libgettextpo0, libasprintf0v5, libgettextpo-dev, libasprintf-dev
Architecture: any all
Version: 0.21-12
Maintainer: Santiago Vila <sanvila@debian.org>
Homepage: https://www.gnu.org/software/gettext/
Standards-Version: 4.6.2
Build-Depends: bison, debhelper-compat (= 13), default-jdk [!hppa !hurd-i386 !kfreebsd-any] <!nojava>, dh-exec (>= 0.13), file, groff, help2man, libunistring-dev, libxml2-dev, maven-repo-helper [!hppa !hurd-i386 !kfreebsd-any] <!nojava>, xz-utils
Build-Depends-Indep: dh-sequence-elpa
Package-List:
 autopoint deb devel optional arch=all
 gettext deb devel optional arch=any
 gettext-base deb utils standard arch=any
 gettext-doc deb doc optional arch=all
 gettext-el deb editors optional arch=all
 libasprintf-dev deb libdevel optional arch=any
 libasprintf0v5 deb libs optional arch=any
 libgettextpo-dev deb libdevel optional arch=any
 libgettextpo0 deb libs optional arch=any
Checksums-Sha1:
 9d75b47baed1a612c0120991c4b6d9cf95e0d430 9714352 gettext_0.21.orig.tar.xz
 b56f3358813526db83269ca2b2edc233b2115d59 819 gettext_0.21.orig.tar.xz.asc
 23ef94656ace18e1342c131033a66f5c3b15ba8f 39008 gettext_0.21-12.debian.tar.xz
Checksums-Sha256:
 d20fcbb537e02dcf1383197ba05bd0734ef7bf5db06bdb241eb69b7d16b73192 9714352 gettext_0.21.orig.tar.xz
 d2587b13a73000e67bce860106c55b726c3e6b5bad06390d073f077334f4b5f3 819 gettext_0.21.orig.tar.xz.asc
 b4bb3a1749f14ea9f3544c3457f934005b0fd130e546fb56fcf9c38d6b5c614b 39008 gettext_0.21-12.debian.tar.xz
Files:
 40996bbaf7d1356d3c22e33a8b255b31 9714352 gettext_0.21.orig.tar.xz
 532b6937f73151c0f4b2d633c9934c87 819 gettext_0.21.orig.tar.xz.asc
 b888d0abd43e450e0599d18e8c3aab37 39008 gettext_0.21-12.debian.tar.xz

-----BEGIN PGP SIGNATURE-----

iQEzBAEBCgAdFiEE1Uw7+v+wQt44LaXXQc5/C58bizIFAmP7fggACgkQQc5/C58b
izK84AgAghahPJtJTmSqqEAl5OONSjNFRoyayqHJuhGcgGUAot7NptEXXZfJ/2Nm
R+/WnymnHiC2KW+1dsCSk4hCAtKx+PoQvueuh94+p2NUBj/JEXKkcg0Ehjav2eP+
Dzp65lAnkiQEnAHQjlqItBRIDEYCfe/jqAR2PlRdI7S7RocEqKS6dQATnFTcBDta
pUgzKPTg3TED9jPwXb+Ug6aVLHTD8jutNpCb0gFjxunvWeaEbl+gXly/tHuj9qNe
3JoxnbBrEXDmdEtEDusuYL7u7kmC+ZUu5a/c0CEt+3AulESNQXzZ2rJyyy0frBqt
YSJY/h2119BdueXSbleHCkgT3N6YXA==
=72mX
-----END PGP SIGNATURE-----
