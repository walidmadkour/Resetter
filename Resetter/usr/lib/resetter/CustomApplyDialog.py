#!/usr/bin/env python
# -*- coding: utf-8 -*-

import apt
import apt.package
import logging
import os
import subprocess
import sys
import threading
import time
from PyQt4 import QtCore, QtGui

import apt_pkg
from Account import AccountDialog
from AptProgress import UIAcquireProgress, UIInstallProgress
from InstallMissingDialog import Install


class ProgressThread(QtCore.QThread):
    def __init__(self, file_in, install):
        QtCore.QThread.__init__(self)
        self.op_progress = None
        self._cache = apt.Cache(self.op_progress)
        self._cache.open()
        self.file_in = file_in
        self.isDone = False
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler('/var/log/resetter/resetter.log')
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        QtGui.qApp.processEvents()
        apt_pkg.init()
        self.install = install
        self.broken_list = []


    def file_len(self):
        try:
            p = subprocess.Popen(['wc', '-l', self.file_in], stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE)
            result, err = p.communicate()
            return int(result.strip().split()[0])
        except subprocess.CalledProcessError:
            pass

    def run(self):
        if self.file_len() != 0:
            loading = 0
            x = float(100) / self.file_len()
            with open(self.file_in) as packages:
                for pkg_name in packages:
                    try:
                        loading += x
                        self.pkg = self._cache[pkg_name.strip()]
                        self.pkg.mark_delete(True, True)
                        self.emit(QtCore.SIGNAL('updateProgressBar(int, bool)'), loading, self.isDone)
                    except (KeyError, SystemError) as error:
                        self.logger.error("{}".format(error))
                        if self.pkg.is_inst_broken or self.pkg.is_now_broken:
                            self.broken_list.append(self.pkg.fullname)
                        self.logger.critical("{}".format(error))
                        continue
                self.isDone = True
                self.emit(QtCore.SIGNAL('updateProgressBar(int, bool)'), 100, self.isDone)
        else:
            print "All removable packages are already removed"
            self.emit(QtCore.SIGNAL('updateProgressBar(int, bool)'), 100, True)


class Apply(QtGui.QDialog):
    def __init__(self, file_in, response, parent=None):
        super(Apply, self).__init__(parent)
        self.setMinimumSize(400, 250)
        self.file_in = file_in
        self.response = response
        self.setWindowTitle("Applying")
        self.error_msg = QtGui.QMessageBox()
        self.error_msg.setIcon(QtGui.QMessageBox.Critical)
        self.error_msg.setWindowTitle("Error")
        self.buttonCancel = QtGui.QPushButton()
        self.buttonCancel.setText("Cancel")
        self.buttonCancel.clicked.connect(self.cancel)
        self.progress = QtGui.QProgressBar(self)
        self.lbl1 = QtGui.QLabel()
        gif = os.path.abspath("/usr/lib/resetter/data/icons/chassingarrows.gif")
        self.movie = QtGui.QMovie(gif)
        self.movie.setScaledSize(QtCore.QSize(20, 20))
        self.pixmap = QtGui.QPixmap("/usr/lib/resetter/data/icons/checkmark.png")
        self.pixmap2 = self.pixmap.scaled(20, 20)
        verticalLayout = QtGui.QVBoxLayout(self)
        verticalLayout.addWidget(self.lbl1)
        verticalLayout.addWidget(self.progress)
        gridLayout = QtGui.QGridLayout()
        self.labels = {}
        for i in range(1, 7):
            for j in range(1, 3):
                self.labels[(i, j)] = QtGui.QLabel()
                self.labels[(i, j)].setMinimumHeight(20)
                gridLayout.addWidget(self.labels[(i, j)], i, j)
        gridLayout.setAlignment(QtCore.Qt.AlignCenter)
        self.labels[(1, 2)].setText("Loading packages")
        self.labels[(2, 2)].setText("Removing packages")
        self.labels[(3, 2)].setText("Cleaning Up")
        self.labels[(4, 2)].setText("Installing packages")
        if self.response:
            self.labels[(5, 2)].setText("Removing old kernels")
            self.labels[(6, 2)].setText("Deleting Users")
        else:
            self.labels[(5, 2)].setText("Deleting Users")

        verticalLayout.addSpacing(20)
        verticalLayout.addLayout(gridLayout)
        verticalLayout.addWidget(self.buttonCancel, 0, QtCore.Qt.AlignRight)
        self.logger = logging.getLogger(__name__)
        self.logger.setLevel(logging.DEBUG)
        handler = logging.FileHandler('/var/log/resetter/resetter.log')
        handler.setLevel(logging.DEBUG)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(funcName)s - %(levelname)s - %(message)s')
        handler.setFormatter(formatter)
        self.logger.addHandler(handler)
        self.progressView = ProgressThread(self.file_in, False)
        self.account = AccountDialog()
        self.connect(self.progressView, QtCore.SIGNAL("updateProgressBar(int, bool)"), self.updateProgressBar)
        self._cache = self.progressView._cache
        self.aprogress = UIAcquireProgress(self.progress, self.lbl1, False)
        self.iprogress = UIInstallProgress(self.progress, self.lbl1)
        self.addUser()

    def addUser(self):
        choice = QtGui.QMessageBox.question \
            (self, 'Would you like set your new account?',
             "Set your own account? Click 'No' so that I can create a default account for you instead",
             QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        if choice == QtGui.QMessageBox.Yes:
            self.show()
            self.account.exec_()
            self.start()
            self.showMinimized()
            print "Adding custom user"

        if choice == QtGui.QMessageBox.No:
            print "Adding default user"
            try:
                p = subprocess.Popen(['bash', '/usr/lib/resetter/data/scripts/new-user.sh'], stderr=subprocess.STDOUT,
                                     stdout=subprocess.PIPE)
                self.logger.info("Default user added")
                p.wait()
                self.start()
            except subprocess.CalledProcessError as e:
                self.logger.error("unable to add default user [{}]".format(e.output), exc_info=True)
                print e.output

    def start(self):
        self.progressView.start()

    def updateProgressBar(self, percent, isdone):
        self.lbl1.setText("Loading Package List")
        self.progress.setValue(percent)
        self.labels[(1, 1)].setMovie(self.movie)
        self.movie.start()
        if isdone:
            self.labels[(1, 1)].setPixmap(self.pixmap2)
            self.movie.stop()
            self.labels[(2, 1)].setMovie(self.movie)
            self.movie.start()
            self.removePackages()

    def cancel(self):
        self.logger.warning("Progress thread was cancelled")
        self.progressView.terminate()
        self.close()

    def removePackages(self):
        self.logger.info("Removing Programs")
        try:
            self.getDependencies()
            self.logger.info("Keep Count before commit: {}".format(self._cache.keep_count))
            self.logger.info("Delete Count before commit: {}".format(self._cache.delete_count))
            self.logger.info("Broken Count before commit: {}".format(self._cache.broken_count))
            if len(self.progressView.broken_list) > 0:
                self.showMessage()
            self._cache.commit(self.aprogress, self.iprogress)
            self.logger.info("Broken Count after commit: {}".format(self._cache.broken_count))
            self.movie.stop()
            self.labels[(2, 1)].setPixmap(self.pixmap2)
            self.progress.setValue(100)
            self.fixBroken()
        except Exception as arg:
            self.movie.stop()
            self.logger.error("Sorry, package removal failed [{}]".format(str(arg)))
            self.error_msg.setText("Something went wrong... please check details")
            self.error_msg.setDetailedText("Package removal failed [{}]".format(str(arg)))
            self.error_msg.exec_()

    def fixBroken(self):
        try:
            self.lbl1.setText("Cleaning up...")
            self.logger.info("Cleaning up...")
            self.labels[(3, 1)].setMovie(self.movie)
            self.progress.setRange(0, 0)

            self.movie.start()
            self.setCursor(QtCore.Qt.BusyCursor)
            self.process = QtCore.QProcess()
            self.process.finished.connect(self.onFinished)
            self.process.start('bash', ['/usr/lib/resetter/data/scripts/fix-broken.sh'])
        except Exception as e:
            self.logger.error("error occured during fix-broken [{}]".format(str(e)))
            self.error_msg.setText("Please make sure other package managers aren't running")
            self.error_msg.exec_()

    def onFinished(self, exit_code, exit_status):
        if exit_code or exit_status != 0:
            self.progress.setRange(0, 1)
            self.logger.error("fixBroken() finished with exit code: {} and exit_status {}."
                              .format(exit_code, exit_status))
        else:
            self.progress.setRange(0, 1)
            self.progress.setValue(1)
            self.logger.debug("Cleanup finished with exit code: {} and exit_status {}.".format(exit_code, exit_status))
            self.movie.stop()
            self.labels[(3, 1)].setPixmap(self.pixmap2)
            self.unsetCursor()
            self.lbl1.setText("Done Cleanup")
            self.installPackages()
            self.removeOldKernels(self.response)

    def installPackages(self):
        self.logger.info("Starting kernel removal...")
        self.labels[(4, 1)].setMovie(self.movie)
        self.movie.start()
        self.install = Install("custom-install", "Installing packages", True)
        self.install.show()
        self.install.exec_()
        self.labels[(4, 1)].setPixmap(self.pixmap2)

    def removeOldKernels(self, response):
        if response:
            self.logger.info("Starting kernel removal...")
            self.labels[(5, 1)].setMovie(self.movie)
            self.movie.start()
            self.setCursor(QtCore.Qt.BusyCursor)
            self._cache.clear()
            self.progress.setValue(0)
            try:
                self.logger.info("Removing old kernels...")
                self.install = Install("Kernels","removing old kernels", False)
                self.install.show()
                self.install.exec_()
                self.labels[(5, 1)].setPixmap(self.pixmap2)
                self.unsetCursor()
                self.lbl1.setText("Finished")
            except Exception as arg:
                self.logger.error("Kernel removal failed [{}]".format(str(arg)))
                print "Sorry, kernel removal failed [{}]".format(str(arg))
            self.removeUsers(response)
            self.showUserInfo()
            self.progress.setValue(1)

        else:
            self.lbl1.setText("Finished")
            self.removeUsers(response)
            self.progress.setValue(1)
            self.showUserInfo()
            self.logger.info("Old kernel removal option not chosen")

    def removeUsers(self, response):
        if response:
            self.logger.info("Starting user removal")
            self.labels[(6, 1)].setMovie(self.movie)
            self.movie.start()
            try:
                subprocess.Popen(['bash', 'custom-users-to-delete.sh'], stderr=subprocess.STDOUT,
                                 stdout=subprocess.PIPE)
                self.logger.debug("user removal completed successfully: [{}]".format(subprocess.STDOUT))
            except subprocess.CalledProcessError, e:
                self.logger.error("unable removing user [{}]".format(e.output))
            self.movie.stop()
            self.labels[(6, 1)].setPixmap(self.pixmap2)
        else:
            self.logger.info("Starting user removal")
            self.labels[(5, 1)].setMovie(self.movie)
            self.movie.start()
            try:
                subprocess.Popen(['bash', 'custom-users-to-delete.sh'], stderr=subprocess.STDOUT,
                                 stdout=subprocess.PIPE)
                self.logger.debug("user removal completed successfully: [{}]".format(subprocess.STDOUT))
            except subprocess.CalledProcessError, e:
                self.logger.error("unable removing user [{}]".format(e.output))
            self.movie.stop()
            self.labels[(5, 1)].setPixmap(self.pixmap2)

    def getDependencies(self):
        try:
            self.setCursor(QtCore.Qt.WaitCursor)
            sq = '\''
            col = ':'
            with open("deplist2", "w") as dl:
                for pkg in self._cache.get_changes():
                    dependencies = pkg.versions[0].dependencies
                    for dependency in dependencies:
                        dependency = str(dependency).split(sq, 1)[1].split(sq, 1)[0]
                        if col in dependency:
                            dependency = dependency.split(col, 1)[0]
                        dl.write('{}\n'.format(dependency))
            with open("keep", "w") as output, open("deplist2", "r") as dl, open(self.file_in, "r") as apps:
                diff = set(dl).difference(apps)
                for line in diff:
                    output.writelines(line)
            self.unsetCursor()
        except Exception as e:
            self.unsetCursor()
            self.logger.error("getting Dependencies failed: {}".format(e))

    def rebootMessage(self):
        choice = QtGui.QMessageBox.information \
            (self, 'Please reboot to complete system changes',
             "Reboot now?",
             QtGui.QMessageBox.Yes | QtGui.QMessageBox.No)
        if choice == QtGui.QMessageBox.Yes:
            self.logger.info("system rebooted after package removals")
            os.system('reboot')
        else:
            self.logger.info("reboot was delayed.")

    def showMessage(self):
        msg = QtGui.QMessageBox(self)
        msg.setWindowTitle("Packages kept back")
        msg.setIcon(QtGui.QMessageBox.Information)
        msg.setText("These packages could cause problems if removed so they've been kept back.")
        text = "\n".join(self.progressView.broken_list)
        msg.setInformativeText(text)
        msg.exec_()

    def showUserInfo(self):
        msg = QtGui.QMessageBox(self)
        msg.setWindowTitle("User Credentials")
        msg.setIcon(QtGui.QMessageBox.Information)
        msg.setText("Please use these credentials the next time you log-in")
        msg.setInformativeText(
            "USERNAME: <b>{}</b><br/> PASSWORD: <b>{}</b>".format(self.account.getUser(), self.account.getPassword()))
        msg.setDetailedText("If you deleted your old user account, "
                            "this account will be the only local user on your system")
        msg.exec_()
        self.logger.info("Credential message info shown")
        self.rebootMessage()
