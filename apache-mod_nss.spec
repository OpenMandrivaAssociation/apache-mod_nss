%define nss_version 3.12.3
%define nssdir %{_sysconfdir}/pki/nss/apache-mod_nss

Summary:	Provides SSL support using the NSS crypto libraries
Name:		apache-mod_nss
Version:	1.0.8
Release:	%mkrel 4
License:	Apache License
Group:		System/Servers
URL:		http://directory.fedora.redhat.com/wiki/Mod_nss
Source0:	http://directory.fedora.redhat.com/sources/mod_nss-%{version}.tar.gz
Patch1:		mod_nss-1.0.3-gencert_fix.diff
Patch2:		mod_nss-wouldblock.patch
Requires(pre): rpm-helper
Requires(postun): rpm-helper
Requires(pre):	apache-conf >= 2.2.0
Requires(pre):	apache >= 2.2.0
Requires:	nss = 2:%{nss_version}
Requires:	ksh
Requires:	openssl
Requires:	apache-conf >= 2.2.0
Requires:	apache >= 2.2.0
BuildRequires:	apache-devel >= 2.2.0
BuildRequires:	automake1.7
BuildRequires:	libnspr-devel >= 2:4.6.5
BuildRequires:	libnss-devel >= 2:%{nss_version}
BuildRequires:	pkgconfig
BuildRequires:  flex
Conflicts:	apache-mod_ssl apache-mod_ssl+distcache
BuildRoot:	%{_tmppath}/%{name}-%{version}-%{release}-buildroot

%description
An Apache 2.0 module for implementing crypto using the Mozilla NSS crypto
libraries. This supports SSLv3/TLSv1 including support for client certificate
authentication. NSS provides web applications with a FIPS 140 certified crypto
provider and support for a full range of PKCS11 devices.

mod_nss is an SSL provider derived from the mod_ssl module for the Apache web
server that uses the Network Security Services (NSS) libraries. We started with
mod_ssl and replaced the OpenSSL calls with NSS calls. 

The mod_ssl package was created in April 1998 by Ralf S. Engelschall and was
originally derived from the Apache-SSL package developed by Ben Laurie. It is
licensed under the Apache 2.0 license.

%prep

%setup -q -n mod_nss-%{version}
%patch1 -p0
%patch2 -p1 -b .wouldblock

%build
export WANT_AUTOCONF_2_5="1"
rm -rf autom*cache configure
libtoolize --copy --force; aclocal-1.7; autoconf; automake-1.7 --foreign --add-missing --copy

if [ -x %{_bindir}/apr-config ]; then APR=%{_bindir}/apr-config; fi
if [ -x %{_bindir}/apr-1-config ]; then APR=%{_bindir}/apr-1-config; fi

export CPPFLAGS=`$APR --cppflags`

%configure2_5x --localstatedir=/var/lib \
    --with-apr-config=$APR \
    --with-apxs=%{_sbindir}/apxs \
    --with-nspr-inc=`pkg-config --cflags nspr | sed 's/^\-I//'` \
    --with-nspr-lib=%{_libdir} \
    --with-nss-inc=`pkg-config --cflags nss | awk '{ print $1}' | sed 's/^\-I//'` \
    --with-nss-lib=%{_libdir}

%make

%install
rm -rf %{buildroot}

install -d %{buildroot}%{_sbindir}
install -d %{buildroot}%{_libdir}/apache-extramodules
install -d %{buildroot}%{nssdir}
install -d %{buildroot}%{_sysconfdir}/httpd/modules.d

install -m0755 .libs/libmodnss.so %{buildroot}%{_libdir}/apache-extramodules/mod_nss.so
install -m0755 nss_pcache %{buildroot}%{_sbindir}/
install -m0755 gencert %{buildroot}%{_sbindir}/nss_gencert

cat > 40_mod_nss.conf << EOF
<IfDefine HAVE_NSS>
    <IfModule !mod_nss.c>
	LoadModule nss_module	extramodules/mod_nss.so
    </IfModule>
</IfDefine>

EOF

# fix the bundled conf
cp nss.conf.in nss.conf.tmp
perl -pi -e "s|\@apache_bin\@|%{_sbindir}|g" nss.conf.tmp
perl -pi -e "s|\@apache_prefix\@/htdocs|/var/www/html|g" nss.conf.tmp
perl -pi -e "s|\@apache_prefix\@/logs|logs|g" nss.conf.tmp
perl -pi -e "s|\@apache_conf\@|%{nssdir}|g" nss.conf.tmp
perl -pi -e "s|\@apache_prefix\@/cgi-bin|/var/www/cgi-bin|g" nss.conf.tmp

# user has to fix this...
perl -pi -e "s|^#NSSOCSP off|#NSSOCSP off\n\nNSSEnforceValidCerts off\n|g" nss.conf.tmp

cat nss.conf.tmp >> 40_mod_nss.conf

install -m0644 40_mod_nss.conf %{buildroot}%{_sysconfdir}/httpd/modules.d/

%post
# http://www.mozilla.org/projects/security/pki/nss/tools/certutil.html
# http://www.mozilla.org/projects/security/pki/nss/tools/pk12util.html
# http://directory.fedora.redhat.com/wiki/Mod_nss

# the following stuff is partly taken from the migrate.pl script and is not the slightest fool proof in any way...

# TODO: figure out how to make this accept a ASCII password file for rpm install automation, currently it 
# prompts for a password which is not so nice.

# Create an NSS database. You just need to specify the database directory, not a specific file. 
# This will create the 3 files that make up your database: cert8.db, key3.db and secmod.db.
if ! [ -f %{nssdir}/cert8.db -o -f %{nssdir}/key3.db -o -f %{nssdir}/secmod.db ]; then
    echo "Creating NSS certificate database."
    certutil -N -d %{nssdir}
fi

# Convert the OpenSSL key and certificate into a PKCS#12 file
if [ -f %{_sysconfdir}/ssl/apache/server.crt -o -f %{_sysconfdir}/ssl/apache/server.key ]; then
    subject=`openssl x509 -subject < %{_sysconfdir}/ssl/apache/server.crt | head -1 | perl -pi -e 's/subject= \///;s/\//,/g;s/Email=.*(,){0,1}//;s/,$//;g'`
    echo "Importing certificate $subject as \"Server-Cert\"."
    openssl pkcs12 -export -in %{_sysconfdir}/ssl/apache/server.crt -inkey %{_sysconfdir}/ssl/apache/server.key \
    -out %{nssdir}/server.p12 -name "Server-Cert" -passout pass:foo
    # Load the PKCS #12 file into your NSS database. 
    pk12util -i %{nssdir}/server.p12 -d %{nssdir} -W foo
else
    %{_sbindir}/nss_gencert %{nssdir}
fi

if [ -f %{_var}/lock/subsys/httpd ]; then
    %{_initrddir}/httpd restart 1>&2;
fi

%postun
if [ "$1" = "0" ]; then
    if [ -f %{_var}/lock/subsys/httpd ]; then
        %{_initrddir}/httpd restart 1>&2
    fi
fi

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
%doc LICENSE NOTICE README TODO migrate.pl docs/*.html
%dir %attr(0750,root,root) %{nssdir}
%attr(0644,root,root) %config(noreplace) %{_sysconfdir}/httpd/modules.d/*_mod_nss.conf
%attr(0755,root,root) %{_sbindir}/nss_pcache
%attr(0755,root,root) %{_sbindir}/nss_gencert
%attr(0755,root,root) %{_libdir}/apache-extramodules/mod_nss.so
