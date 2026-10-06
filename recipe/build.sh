set -eux
# Install Python code:
python -m pip install -vv .
# Sync etc/:
mkdir -pv $PREFIX/etc
rsync -av $RECIPE_DIR/etc/ $PREFIX/etc/
# Copy files needed during test phase:
dst=../test_files
rm -fr $dst
mkdir -pv $dst
mv -v $PKG_NAME $dst/
ln -s $dst/$PKG_NAME
cp -v $SRC_DIR/pyproject.toml $dst/
