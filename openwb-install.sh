#!/bin/bash
OPENWBBASEDIR=/var/www/html/openWB
OPENWB_USER=openwb
OPENWB_GROUP=openwb
VENV_DIR="${OPENWBBASEDIR}/venv"
TEMP_REQ="/home/$OPENWB_USER/temp_requirements.txt"

# Lösche temporäre Datei bei Skript-Abbruch
trap 'rm -f "$TEMP_REQ"' EXIT

# Prüfen, ob das Script als Root ausgeführt wird
if (( $(id -u) != 0 )); then
    echo "this script has to be run as user root or with sudo"
    exit 1
fi

echo "installing openWB 2 into \"${OPENWBBASEDIR}\""

# Setze UTF-8 Locale und Zeitzone Berlin
echo "Setze UTF-8 Locale und Zeitzone Europe/Berlin..."
if ! locale -a | grep -q "de_DE.utf8"; then
    echo "Generiere de_DE.UTF-8 Locale..."
    apt-get update
    apt-get install -y locales
    locale-gen de_DE.UTF-8
fi
update-locale LANG=de_DE.UTF-8 LC_ALL=de_DE.UTF-8
timedatectl set-timezone Europe/Berlin
echo "Locale und Zeitzone erfolgreich gesetzt."

# Debian-Version oder Codename erkennen
DEBIAN_VERSION="unknown"
DEBIAN_CODENAME=""

# Zuerst /etc/os-release prüfen (zuverlässiger für moderne Systeme)
if [ -f /etc/os-release ]; then
    . /etc/os-release
    DEBIAN_CODENAME=$VERSION_CODENAME
    case "$DEBIAN_CODENAME" in
        "bullseye")
            DEBIAN_VERSION="11"
            ;;
        "bookworm")
            DEBIAN_VERSION="12"
            ;;
        "trixie")
            DEBIAN_VERSION="13"
            ;;
        "forky")  # Annahme für Debian 14
            DEBIAN_VERSION="14"
            ;;
        "sid")
            DEBIAN_VERSION="unstable"
            ;;
        *)
            DEBIAN_VERSION="unknown"
            ;;
    esac
fi

# Fallback auf /etc/debian_version
if [[ "$DEBIAN_VERSION" == "unknown" && -f /etc/debian_version ]]; then
    DEBIAN_VERSION_RAW=$(cat /etc/debian_version)
    case "$DEBIAN_VERSION_RAW" in
        "11"|"11."*)
            DEBIAN_VERSION="11"
            DEBIAN_CODENAME="bullseye"
            ;;
        "12"|"12."*)
            DEBIAN_VERSION="12"
            DEBIAN_CODENAME="bookworm"
            ;;
        "13"|"13."*)
            DEBIAN_VERSION="13"
            DEBIAN_CODENAME="trixie"
            ;;
        "14"|"14."*)
            DEBIAN_VERSION="14"
            DEBIAN_CODENAME="forky"  # Annahme für Debian 14
            ;;
        "trixie/sid")
            DEBIAN_VERSION="13"
            DEBIAN_CODENAME="trixie"
            ;;
        "sid")
            DEBIAN_VERSION="unstable"
            DEBIAN_CODENAME="sid"
            ;;
        *)
            DEBIAN_VERSION="unknown"
            ;;
    esac
fi

# Fehler, wenn keine Version erkannt wurde
if [[ "$DEBIAN_VERSION" == "unknown" ]]; then
    echo "Fehler: Debian-Version konnte nicht erkannt werden."
    echo "Unterstützte Versionen: Debian 11 (Bullseye), 12 (Bookworm), 13 (Trixie), 14 (Forky), Unstable (Sid)"
    exit 1
fi

echo "Erkannte Debian-Version: $DEBIAN_VERSION (Codename: $DEBIAN_CODENAME)"

# Erweitere Dateisystem auf Raspberry Pi
if [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model; then
    echo "Erkenne Raspberry Pi, erweitere Dateisystem..."
    if command -v raspi-config >/dev/null; then
        raspi-config nonint do_expand_rootfs
        echo "Dateisystem mit raspi-config erfolgreich erweitert."
    else
        echo "raspi-config nicht gefunden, versuche manuelle Erweiterung..."
        ROOT_PART=$(mount | grep "on / " | awk '{print $1}' | sed 's/p[0-9]$//')
        ROOT_PART_NUM=$(mount | grep "on / " | awk '{print $1}' | grep -o '[0-9]$')
        if [ -n "$ROOT_PART" ] && [ -n "$ROOT_PART_NUM" ]; then
            echo -e "d\n$ROOT_PART_NUM\nn\np\n$ROOT_PART_NUM\n\n\nw" | fdisk "$ROOT_PART"
            partprobe
            resize2fs "${ROOT_PART}p${ROOT_PART_NUM}"
            echo "Dateisystem manuell erfolgreich erweitert."
        else
            echo "Fehler: Root-Partition konnte nicht erkannt werden, überspringe Erweiterung."
        fi
    fi
else
    echo "Kein Raspberry Pi erkannt, überspringe Dateisystemerweiterung."
fi

# Installiere python3-pip für Debian 11
if [[ "$DEBIAN_VERSION" == "11" ]]; then
    echo "Installiere python3-pip für Debian 11..."
    apt-get update
    apt-get install -y python3-pip
    echo "python3-pip erfolgreich installiert."
fi

# Installationspakete über Script installieren
curl -s "https://raw.githubusercontent.com/Xerolux/OpenWB2-Bookworm-Trixie/master/runs/install_packages.sh" | bash -s
if [ $? -ne 0 ]; then
    echo "Versuche lokales install_packages.sh..."
    bash ./install_packages.sh
fi

# Installiere Build-Tools und python3-dev für Debian 12, 13, 14 und unstable
if [[ "$DEBIAN_VERSION" == "12" || "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]]; then
    echo "Installiere Build-Tools und python3-dev für Debian $DEBIAN_VERSION..."
    apt-get update
    apt-get install -y autoconf automake build-essential libtool python3-dev
    echo "Build-Tools und python3-dev erfolgreich installiert."
fi

# Installiere libxml2, libxslt und Entwicklungspakete für Debian 12, 13, 14 und höher
if [[ "$DEBIAN_VERSION" =~ ^[0-9]+$ ]] && [[ "$DEBIAN_VERSION" -ge 12 ]]; then
    echo "Installiere libxml2, libxslt und Entwicklungspakete für Debian $DEBIAN_VERSION..."
    apt-get install -y libxml2 libxslt1.1 libxml2-dev libxslt1-dev
    echo "libxml2, libxslt und Entwicklungspakete erfolgreich installiert."
fi

# Installiere python3-venv und version-spezifische venv-Pakete
echo "Installiere python3-venv und version-spezifische Abhängigkeiten..."
apt-get update
apt-get install -y python3-venv

# Erkenne die Python-Version und installiere das entsprechende venv-Paket
PYTHON_VERSION=$(/usr/bin/python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
PYTHON_VENV_PKG="python${PYTHON_VERSION}-venv"
if [[ "$DEBIAN_VERSION" == "12" || "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]]; then
    echo "Installiere $PYTHON_VENV_PKG für Debian $DEBIAN_VERSION..."
    apt-get install -y "$PYTHON_VENV_PKG"
    if [ $? -ne 0 ]; then
        echo "Fehler: Konnte $PYTHON_VENV_PKG nicht installieren. Überprüfe die Paketquellen."
        exit 1
    fi
fi
echo "python3-venv und $PYTHON_VENV_PKG erfolgreich installiert."

# Prüfe, ob das venv-Modul verfügbar ist
echo "Prüfe Verfügbarkeit des venv-Moduls..."
if ! /usr/bin/python3 -m venv --help >/dev/null 2>&1; then
    echo "Fehler: Das Python venv-Modul ist nicht verfügbar. Überprüfe die Installation von python3-venv und $PYTHON_VENV_PKG."
    exit 1
fi
echo "venv-Modul ist verfügbar."

# Installiere Netzwerk- und Firewall-Pakete
echo "Installiere Netzwerk- und Firewall-Pakete..."
apt-get install -y iptables dhcpcd5 dnsmasq
echo "Netzwerk- und Firewall-Pakete erfolgreich installiert."

# Warnung für Debian 12, 13, 14 und unstable
show_warning() {
    echo "*******************************************************************"
    echo "* ACHTUNG / WARNING *"
    echo "*******************************************************************"
    echo "* Sie möchten eine openWB-Installation auf einem Betriebssystem      *"
    echo "* durchführen, das nur eingeschränkt unterstützt wird. Dies ist eine *"
    echo "* openWB Community Edition ohne Support und ohne Garantie auf        *"
    echo "* Funktion.                                                         *"
    echo "* *"
    echo "* You are about to install openWB on an operating system with        *"
    echo "* limited support. This is an openWB Community Edition without       *"
    echo "* support or warranty of functionality.                              *"
    echo "*******************************************************************"
    echo "Installation wird in 10 Sekunden fortgesetzt..."
    sleep 10
}

if [[ "$DEBIAN_VERSION" == "12" || "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]]; then
    show_warning
fi

echo "create group $OPENWB_GROUP"
/usr/sbin/groupadd "$OPENWB_GROUP"
echo "done"

echo "create user $OPENWB_USER"
/usr/sbin/useradd "$OPENWB_USER" -g "$OPENWB_GROUP" --create-home
echo "done"

echo "$OPENWB_USER ALL=(ALL) NOPASSWD: ALL" > /etc/sudoers.d/openwb
chmod 440 /etc/sudoers.d/openwb
echo "done"

echo "check for initial git clone..."
if [ ! -d "${OPENWBBASEDIR}/web" ]; then
    mkdir -p "$OPENWBBASEDIR"
    chown "$OPENWB_USER:$OPENWB_GROUP" "$OPENWBBASEDIR"
    sudo -u "$OPENWB_USER" git clone https://github.com/Xerolux/OpenWB2-Bookworm-Trixie.git --branch master "$OPENWBBASEDIR"
    echo "git cloned"
else
    echo "ok"
fi

echo -n "check for ramdisk... "
if grep -Fq "tmpfs ${OPENWBBASEDIR}/ramdisk" /etc/fstab; then
    echo "ok"
else
    mkdir -p "${OPENWBBASEDIR}/ramdisk"
    sudo tee -a "/etc/fstab" <"${OPENWBBASEDIR}/data/config/ramdisk_config.txt" >/dev/null
    mount -a
    echo "created"
fi

echo -n "check for crontab... "
if [ ! -f /etc/cron.d/openwb ]; then
    cp "${OPENWBBASEDIR}/data/config/openwb.cron" /etc/cron.d/openwb
    echo "installed"
else
    echo "ok"
fi

echo "updating mosquitto config file"
systemctl stop mosquitto
sleep 2
cp -a "${OPENWBBASEDIR}/data/config/mosquitto/mosquitto.conf" /etc/mosquitto/mosquitto.conf
mkdir -p /etc/mosquitto/conf.d
cp "${OPENWBBASEDIR}/data/config/mosquitto/openwb.conf" /etc/mosquitto/conf.d/openwb.conf
cp "${OPENWBBASEDIR}/data/config/mosquitto/mosquitto.acl" /etc/mosquitto/mosquitto.acl
sudo cp /etc/ssl/certs/ssl-cert-snakeoil.pem /etc/mosquitto/certs/openwb.pem
sudo cp /etc/ssl/private/ssl-cert-snakeoil.key /etc/mosquitto/certs/openwb.key
sudo chgrp mosquitto /etc/mosquitto/certs/openwb.key
systemctl start mosquitto

if [ ! -f /etc/init.d/mosquitto_local ]; then
    echo "setting up mosquitto local instance"
    install -d -m 0755 -o root -g root /etc/mosquitto/conf_local.d/
    install -d -m 0755 -o mosquitto -g root /var/lib/mosquitto_local
    cp "${OPENWBBASEDIR}/data/config/mosquitto/mosquitto_local_init" /etc/init.d/mosquitto_local
    chown root:root /etc/init.d/mosquitto_local
    chmod 755 /etc/init.d/mosquitto_local
    systemctl daemon-reload
    systemctl enable mosquitto_local
else
    systemctl stop mosquitto_local
    sleep 2
fi
cp -a "${OPENWBBASEDIR}/data/config/mosquitto/mosquitto_local.conf" /etc/mosquitto/mosquitto_local.conf
cp -a "${OPENWBBASEDIR}/data/config/mosquitto/openwb_local.conf" /etc/mosquitto/conf_local.d/
systemctl start mosquitto_local
echo "mosquitto done"

# Installiere Nginx und PHP-FPM
echo "Installiere Nginx und PHP-FPM..."
apt-get install -y nginx php-fpm
if [[ "$DEBIAN_VERSION" == "11" ]]; then
    PHP_FPM_SOCK="/run/php/php7.4-fpm.sock"
elif [[ "$DEBIAN_VERSION" == "12" ]]; then
    PHP_FPM_SOCK="/run/php/php8.2-fpm.sock"
elif [[ "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]]; then
    PHP_FPM_SOCK="/run/php/php8.3-fpm.sock"
else
    PHP_FPM_SOCK="/run/php/php-fpm.sock"
fi
echo "Nginx und PHP-FPM installiert (PHP-FPM Socket: $PHP_FPM_SOCK)."

# Konfiguriere Nginx
echo -n "Konfiguriere Nginx..."
cat > /etc/nginx/sites-available/openwb-ssl << 'EOF'
server {
    listen 443 ssl;
    server_name _;

    ssl_certificate /etc/ssl/certs/ssl-cert-snakeoil.pem;
    ssl_certificate_key /etc/ssl/private/ssl-cert-snakeoil.key;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;
    ssl_prefer_server_ciphers on;

    root /var/www/html;

    error_log /var/log/nginx/error.log;
    access_log /var/log/nginx/access.log combined;

    location /ws {
        proxy_pass http://localhost:9001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }

    location /mqtt {
        proxy_pass http://localhost:9001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "Upgrade";
        proxy_set_header Host $host;
    }

    location /openWB/ {
        allow all;
        try_files $uri $uri/ /index.php?$args;
        index index.php index.html index.htm;
    }

    location /openWB/ramdisk/ {
        autoindex on;
    }

    location /openWB/data/backup/ {
        autoindex on;
    }

    location ~ \.php$ {
        include snippets/fastcgi-php.conf;
        fastcgi_pass unix:PHP_FPM_SOCK;
        fastcgi_param SCRIPT_FILENAME $document_root$fastcgi_script_name;
        include fastcgi_params;
    }

    location ~ /\. {
        deny all;
    }
}
EOF

# Ersetze PHP_FPM_SOCK mit dem korrekten Wert
sed -i "s|fastcgi_pass unix:PHP_FPM_SOCK;|fastcgi_pass unix:$PHP_FPM_SOCK;|" /etc/nginx/sites-available/openwb-ssl

# Aktiviere die Nginx-Konfiguration
ln -sf /etc/nginx/sites-available/openwb-ssl /etc/nginx/sites-enabled/openwb-ssl
rm -f /etc/nginx/sites-enabled/default
echo "done"

# Setze Upload-Limit für PHP
echo -n "Setze PHP Upload-Limit..."
if [[ "$DEBIAN_VERSION" == "11" && -d "/etc/php/7.4/" ]]; then
    echo "upload_max_filesize = 300M" > /etc/php/7.4/fpm/conf.d/20-uploadlimit.ini
    echo "post_max_size = 300M" >> /etc/php/7.4/fpm/conf.d/20-uploadlimit.ini
    echo "done (PHP 7.4 - OS Bullseye)"
elif [[ "$DEBIAN_VERSION" == "12" && -d "/etc/php/8.2/" ]]; then
    echo "upload_max_filesize = 300M" > /etc/php/8.2/fpm/conf.d/20-uploadlimit.ini
    echo "post_max_size = 300M" >> /etc/php/8.2/fpm/conf.d/20-uploadlimit.ini
    echo "done (PHP 8.2 - OS Bookworm)"
elif [[ "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]] && [ -d "/etc/php/8.3/" ]; then
    echo "upload_max_filesize = 300M" > /etc/php/8.3/fpm/conf.d/20-uploadlimit.ini
    echo "post_max_size = 300M" >> /etc/php/8.3/fpm/conf.d/20-uploadlimit.ini
    echo "done (PHP 8.3 - OS Trixie/Sid)"
else
    echo "Fehler: Keine unterstützte PHP-Version gefunden, überspringe Upload-Limit-Konfiguration"
fi

# Starte Nginx und PHP-FPM
echo -n "Starte Nginx und PHP-FPM..."
systemctl enable nginx
systemctl enable php${PYTHON_VERSION}-fpm
systemctl restart nginx
systemctl restart php${PYTHON_VERSION}-fpm
echo "done"

# Erstelle virtuelle Umgebung
if [[ "$DEBIAN_VERSION" == "11" || "$DEBIAN_VERSION" == "12" || "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]]; then
    USE_VENV=true
    echo "Verwende virtuelle Umgebung für Debian $DEBIAN_VERSION, um Konsistenz zu gewährleisten."
else
    USE_VENV=false
fi

if $USE_VENV; then
    # Lösche bestehende virtuelle Umgebung, falls sie beschädigt ist
    if [ -d "$VENV_DIR" ]; then
        echo "Lösche bestehende virtuelle Umgebung in ${VENV_DIR}..."
        rm -rf "$VENV_DIR"
    fi

    # Stelle sicher, dass das Verzeichnis für die virtuelle Umgebung existiert und die richtigen Berechtigungen hat
    mkdir -p "$OPENWBBASEDIR"
    chown "$OPENWB_USER:$OPENWB_GROUP" "$OPENWBBASEDIR"

    echo "Erstelle virtuelle Umgebung in ${VENV_DIR}..."
    if ! sudo -u "$OPENWB_USER" /usr/bin/python3 -m venv "$VENV_DIR"; then
        echo "Fehler: Konnte virtuelle Umgebung nicht erstellen. Details:"
        sudo -u "$OPENWB_USER" /usr/bin/python3 -m venv "$VENV_DIR" 2>&1
        echo "Überprüfe Python-Version, python3-venv Installation und Berechtigungen."
        exit 1
    fi

    # Prüfe, ob die virtuelle Umgebung erstellt wurde
    if [ ! -d "$VENV_DIR" ] || [ ! -f "$VENV_DIR/bin/python" ]; then
        echo "Fehler: Virtuelle Umgebung wurde nicht korrekt erstellt. Verzeichnis oder Python-Binary fehlt."
        exit 1
    fi
    echo "Virtuelle Umgebung erfolgreich erstellt."

    PYTHON_EXEC="$VENV_DIR/bin/python"
    PIP_EXEC="$VENV_DIR/bin/pip"

    # Prüfe, ob pip im Venv existiert
    if [ ! -f "$PIP_EXEC" ]; then
        echo "Warnung: pip nicht in der virtuellen Umgebung gefunden ($PIP_EXEC). Versuche, pip zu installieren..."

        # Prüfe, ob ensurepip verfügbar ist
        if sudo -u "$OPENWB_USER" "$PYTHON_EXEC" -c "import ensurepip" 2>/dev/null; then
            echo "Verwende ensurepip, um pip zu installieren..."
            if ! sudo -u "$OPENWB_USER" "$PYTHON_EXEC" -m ensurepip --upgrade; then
                echo "Fehler: ensurepip konnte pip nicht installieren."
            fi
            if ! sudo -u "$OPENWB_USER" "$PYTHON_EXEC" -m pip install --upgrade pip; then
                echo "Fehler: Konnte pip nicht aktualisieren."
            fi
        else
            echo "ensurepip nicht verfügbar, lade pip manuell herunter..."
            TEMP_PIP_SCRIPT="/tmp/get-pip.py"
            if curl -s https://bootstrap.pypa.io/get-pip.py -o "$TEMP_PIP_SCRIPT"; then
                if ! sudo -u "$OPENWB_USER" "$PYTHON_EXEC" "$TEMP_PIP_SCRIPT"; then
                    echo "Fehler: get-pip.py konnte pip nicht installieren."
                fi
                rm -f "$TEMP_PIP_SCRIPT"
            else
                echo "Fehler: Konnte get-pip.py nicht herunterladen."
                exit 1
            fi
        fi

        # Überprüfe erneut, ob pip installiert wurde
        if [ ! -f "$PIP_EXEC" ]; then
            echo "Fehler: Konnte pip nicht in der virtuellen Umgebung installieren."
            exit 1
        fi
    fi
    echo "pip erfolgreich in der virtuellen Umgebung installiert."

    # Verlinke venv-Binaries direkt nach /bin (ohne Suffix)
    echo "Verlinke virtuelle Umgebung Binaries direkt nach /bin..."
    echo "Warnung: Bestehende System-Binaries in /bin werden überschrieben. Dies kann andere Skripte oder Dienste beeinflussen."
    for binary in python python3 pip pip3; do
        if [ -f "$VENV_DIR/bin/$binary" ]; then
            ln -sf "$VENV_DIR/bin/$binary" "/bin/$binary"
            if [ $? -eq 0 ]; then
                echo "Erfolgreich verlinkt: /bin/$binary -> $VENV_DIR/bin/$binary"
            else
                echo "Fehler: Konnte /bin/$binary nicht verlinken."
                exit 1
            fi
        else
            echo "Fehler: Binary $binary nicht in $VENV_DIR/bin gefunden, Verlinkung abgebrochen."
            exit 1
        fi
    done

    # Prüfe, ob die verlinkten Binaries funktionieren
    for binary in python python3 pip pip3; do
        if ! "/bin/$binary" --version >/dev/null 2>&1; then
            echo "Fehler: Verlinktes Binary /bin/$binary funktioniert nicht."
            exit 1
        fi
    done
    echo "Alle venv-Binaries erfolgreich nach /bin verlinkt und geprüft."
else
    PYTHON_EXEC="/usr/bin/python3"
    PIP_EXEC="/usr/bin/pip3"
fi

# Prüfe System-Binaries
echo "Prüfe Konsistenz der Python- und pip-Binaries..."
if ! command -v python3 >/dev/null || ! command -v python >/dev/null; then
    echo "Fehler: python oder python3 nicht im System gefunden."
    exit 1
fi
SYSTEM_PYTHON3=$(readlink -f $(which python3))
SYSTEM_PYTHON=$(readlink -f $(which python))
if [[ "$SYSTEM_PYTHON3" != "$(readlink -f /bin/python3)" ]]; then
    echo "Warnung: /bin/python3 unterscheidet sich von der System-python3-Binary."
fi
if [[ "$SYSTEM_PYTHON" != "$(readlink -f /bin/python3)" ]]; then
    echo "Warnung: /bin/python3 unterscheidet sich von der System-python-Binary."
fi

# Prüfe pip-Version
SYSTEM_PIP3=$(pip3 --version | grep -o 'pip [0-9.]*' | awk '{print $2}' 2>/dev/null)
if [ -f "$PIP_EXEC" ]; then
    VENV_PIP=$("$PIP_EXEC" --version | grep -o 'pip [0-9.]*' | awk '{print $2}')
    if [[ "$SYSTEM_PIP3" != "$VENV_PIP" ]]; then
        echo "Warnung: pip-Version in venv ($VENV_PIP) unterscheidet sich von System-pip3 ($SYSTEM_PIP3)."
    fi
fi

# Funktion zum Aktualisieren der requirements.txt
update_requirements() {
    echo "Aktualisiere requirements.txt, behalte pymodbus-Version bei..."
    REQUIREMENTS_FILE="${OPENWBBASEDIR}/requirements.txt"
    BACKUP_FILE="${OPENWBBASEDIR}/requirements.txt.bak"
    cp "$REQUIREMENTS_FILE" "$BACKUP_FILE"
    PYMODBUS_LINE=$(grep '^pymodbus==' "$REQUIREMENTS_FILE")
    sudo -u "$OPENWB_USER" "$PIP_EXEC" install --upgrade -r "$REQUIREMENTS_FILE"
    sudo -u "$OPENWB_USER" "$PIP_EXEC" freeze > "$TEMP_REQ"
    if [ -n "$PYMODBUS_LINE" ]; then
        sed -i "/^pymodbus==/d" "$TEMP_REQ"
        echo "$PYMODBUS_LINE" >> "$TEMP_REQ"
    fi
    mv "$TEMP_REQ" "$REQUIREMENTS_FILE"
    echo "requirements.txt aktualisiert, pymodbus-Version beibehalten."
}

# Prüfe installierte Abhängigkeiten
check_requirements() {
    echo "Prüfe, ob alle Abhängigkeiten installiert wurden..."
    while IFS= read -r line; do
        package=$(echo "$line" | cut -d'=' -f1)
        if ! sudo -u "$OPENWB_USER" "$PIP_EXEC" show "$package" > /dev/null; then
            echo "Fehler: Paket $package konnte nicht installiert werden."
            exit 1
        fi
    done < "${OPENWBBASEDIR}/requirements.txt"
    echo "Alle Abhängigkeiten erfolgreich installiert."
}

# Installiere Python-Abhängigkeiten
echo "Installiere Python-Abhängigkeiten..."
if $USE_VENV; then
    if ! sudo -u "$OPENWB_USER" "$PIP_EXEC" install --upgrade pip; then
        echo "Fehler: Konnte pip nicht aktualisieren."
        exit 1
    fi
    if [[ "$DEBIAN_VERSION" == "12" || "$DEBIAN_VERSION" == "13" || "$DEBIAN_VERSION" == "14" || "$DEBIAN_VERSION" == "unstable" ]]; then
        echo "Für Debian $DEBIAN_VERSION: Aktualisiere Abhängigkeiten und installiere..."
        update_requirements
        if ! sudo -u "$OPENWB_USER" "$PIP_EXEC" install -r "${OPENWBBASEDIR}/requirements.txt"; then
            echo "Fehler: Konnte Python-Abhängigkeiten aus requirements.txt nicht installieren."
            exit 1
        fi
        check_requirements
    else
        if ! sudo -u "$OPENWB_USER" "$PIP_EXEC" install -r "${OPENWBBASEDIR}/requirements.txt"; then
            echo "Fehler: Konnte Python-Abhängigkeiten aus requirements.txt nicht installieren."
            exit 1
        fi
        check_requirements
    fi
else
    if ! sudo -u "$OPENWB_USER" "$PIP_EXEC" install --user --upgrade pip; then
        echo "Fehler: Konnte systemweites pip nicht aktualisieren."
        exit 1
    fi
    if ! sudo -u "$OPENWB_USER" "$PIP_EXEC" install --user -r "${OPENWBBASEDIR}/requirements.txt"; then
        echo "Fehler: Konnte Python-Abhängigkeiten für den Benutzer installieren."
        exit 1
    fi
    check_requirements
fi

echo "installing openwb2 system service..."
sed -i "s|ExecStart=.*|ExecStart=$PYTHON_EXEC -m openWB.run|" "${OPENWBBASEDIR}/data/config/openwb2.service"
if ! $USE_VENV; then
    PYTHON_MAJOR_MINOR=$("$PYTHON_EXEC" --version | cut -d' ' -f2 | cut -d'.' -f1,2)
    sed -i "/ExecStart=/i Environment=\"PYTHONPATH=/home/$OPENWB_USER/.local/lib/python${PYTHON_MAJOR_MINOR}/site-packages\"" "${OPENWBBASEDIR}/data/config/openwb2.service"
fi
ln -sf "${OPENWBBASEDIR}/data/config/openwb2.service" /etc/systemd/system/openwb2.service
systemctl daemon-reload
systemctl enable openwb2

echo "installing openwb2 remote support service..."
sed -i "s|ExecStart=.*python|ExecStart=$PYTHON_EXEC|" "${OPENWBBASEDIR}/data/config/openwbRemoteSupport.service"
if ! $USE_VENV; then
    sed -i "/ExecStart=/i Environment=\"PYTHONPATH=/home/$OPENWB_USER/.local/lib/python${PYTHON_MAJOR_MINOR}/site-packages\"" "${OPENWBBASEDIR}/data/config/openwbRemoteSupport.service"
fi
cp "${OPENWBBASEDIR}/data/config/openwbRemoteSupport.service" /etc/systemd/system/openwbRemoteSupport.service
systemctl daemon-reload
systemctl enable openwbRemoteSupport
systemctl start openwbRemoteSupport

echo "installation finished, now starting openwb2.service..."
systemctl start openwb2

# Systemoptimierung
echo "Optimiere System..."
# APT aufräumen
apt-get autoclean
apt-get autoremove -y
echo "APT Cache und ungenutzte Pakete bereinigt."

# Python-Cache löschen
find "$OPENWBBASEDIR" -type d -name "__pycache__" -exec rm -rf {} +
find "/home/$OPENWB_USER/.local" -type d -name "__pycache__" -exec rm -rf {} +
find "$OPENWBBASEDIR" -type f -name "*.pyc" -delete
find "$OPENWBBASEDIR" -type f -name "*.pyo" -delete
find "/home/$OPENWB_USER/.local" -type f -name "*.pyc" -delete
find "/home/$OPENWB_USER/.local" -type f -name "*.pyo" -delete
echo "Python-Cache erfolgreich gelöscht."

# Speicheroptimierungen (nur auf Raspberry Pi)
if [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model; then
    echo "vm.swappiness=10" > /etc/sysctl.d/99-openwb.conf
    echo "vm.vfs_cache_pressure=200" >> /etc/sysctl.d/99-openwb.conf
    sysctl -p /etc/sysctl.d/99-openwb.conf
    echo "Speicheroptimierungen (Swappiness, VFS Cache) angewendet (nur Raspberry Pi)."
else
    echo "Kein Raspberry Pi erkannt, überspringe Speicheroptimierungen."
fi

# Journal-Logs bereinigen
journalctl --vacuum-time=7d
echo "Systemd Journal-Logs älter als 7 Tage bereinigt."

# Deaktiviere unnötige Dienste auf Raspberry Pi
if [ -f /proc/device-tree/model ] && grep -q "Raspberry Pi" /proc/device-tree/model; then
    if systemctl is-active --quiet bluetooth; then
        systemctl disable bluetooth
        systemctl stop bluetooth
        echo "Bluetooth-Dienst deaktiviert."
    fi
fi

# Konfiguriere tmpfs für /tmp und /var/log
if ! grep -q "/tmp" /etc/fstab; then
    echo "tmpfs /tmp tmpfs defaults,noatime,nosuid,nodev 0 0" >> /etc/fstab
fi
if ! grep -q "/var/log" /etc/fstab; then
    echo "tmpfs /var/log tmpfs defaults,noatime,nosuid,nodev 0 0" >> /etc/fstab
fi
mount -a
echo "tmpfs für /tmp und /var/log konfiguriert."

echo "Systemoptimierung abgeschlossen."
echo "all done"
echo "if you want to use this installation for development, add a password for user 'openwb' with: sudo passwd openwb"
