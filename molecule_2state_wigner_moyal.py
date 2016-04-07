import numpy as np

# numpy.fft has better implementation of real fourier transform
# necessary for real split operator propagator
from numpy import fft
from scipy import fftpack # Tools for fourier transform


class Molecule2StateWignerMoyal:
    """
    Coherent (no open system effects) split-operator for the Wigner phase space representation of
    the two state approximation for molecular dynamics, where the molecular hamiltonian is assumed

        H = K(p) + [Vg(x) + Ve(x)]/2 + sigma_x Veg(x,t) + sigma_z [Vg(x) - Ve(x)]/2,

    where sigma_x and sigma_z are Pauli matrices, Vg(x) [Ve(x)] is the ground (excited)
    state adiabatic potential curve, and Veg(x,t) is the laser-molecule interaction energy.
    """
    def __init__(self, **kwargs):
        """
        The following parameters must be specified
            X_gridDIM - the coordinate grid size
            X_amplitude - maximum value of the coordinates
            P_gridDIM - the momentum grid size
            P_amplitude - maximum value of the momentum
            Vg(x) - the ground electronic state adiabatic potential curve
            Ve(x) - the first excited electronic state adiabatic potential curve
            Veg(x) - coupling between ground and excited states (may be time dependent), e.g.,
                    via laser-molecule interaction
            K(p) - kinetic energy
            dt - time step
            t (optional) - initial value of time
        """
        # save all attributes
        for name, value in kwargs.items():
            setattr(self, name, value)

        # Check that all attributes were specified
        try:
            self.X_gridDIM
        except AttributeError:
            raise AttributeError("Coordinate grid size (X_gridDIM) was not specified")

        assert self.X_gridDIM % 2 == 0, "Coordinate grid size (X_gridDIM) must be even"

        try:
            self.P_gridDIM
        except AttributeError:
            raise AttributeError("Momentum grid size (P_gridDIM) was not specified")

        assert self.P_gridDIM % 2 == 0, "Momentum grid size (P_gridDIM) must be even"

        try:
            self.X_amplitude
        except AttributeError:
            raise AttributeError("Coordinate grid range (X_amplitude) was not specified")

        try:
            self.P_amplitude
        except AttributeError:
            raise AttributeError("Momentum grid range (P_amplitude) was not specified")

        try:
            self.Vg
            self.Ve
            self.Veg
        except AttributeError:
            raise AttributeError("Potential energies (Vg, Ve, Veg) was not specified")

        try:
            self.K
        except AttributeError:
            raise AttributeError("The kinetic energy (K) was not specified")

        try:
            self.dt
        except AttributeError:
            raise AttributeError("Time-step (dt) was not specified")

        try:
            self.t
        except AttributeError:
            print("Warning: Initial time (t) was not specified, thus it is set to zero.")
            self.t = 0.

        # get coordinate and momentum step sizes
        self.dX = 2.*self.X_amplitude / self.X_gridDIM
        self.dP = 2.*self.P_amplitude / self.P_gridDIM

        # coordinate grid
        self.X = np.linspace(-self.X_amplitude, self.X_amplitude - self.dX , self.X_gridDIM)
        self.X = self.X[np.newaxis, :]

        # Lambda grid (variable conjugate to the coordinate)
        self.Lambda = fft.fftfreq(self.X_gridDIM, self.dX/(2*np.pi))

        # take only first half, as required by the real fft
        #self.Lambda = self.Lambda[:(1 + self.X_gridDIM//2)]
        #
        self.Lambda = self.Lambda[np.newaxis, :]

        # momentum grid
        self.P = np.linspace(-self.P_amplitude, self.P_amplitude - self.dP, self.P_gridDIM)
        self.P = self.P[:, np.newaxis]

        # Theta grid (variable conjugate to the momentum)
        self.Theta = fft.fftfreq(self.P_gridDIM, self.dP/(2*np.pi))

        # take only first half, as required by the real fft
        #self.Theta = self.Theta[:(1 + self.P_gridDIM//2)]
        #
        self.Theta = self.Theta[:, np.newaxis]

        # Save shifted grids
        self.x_plus = self.X + 0.5*self.Theta
        self.x_minus = self.X - 0.5*self.Theta

        # Pre-calculate the potential energy difference
        self._Vg_plus_Ve_x_plus = self.Vg(self.x_plus) - self.Ve(self.x_plus)
        self._Vg_minus_Ve_x_minus = self.Vg(self.x_minus) - self.Ve(self.x_minus)

        # Pre-calculate the potential energy phase
        self.expV = self.Vg(self.x_plus) - self.Vg(self.x_minus) + self.Ve(self.x_plus) - self.Ve(self.x_minus)
        self.expV = 0.5*1j*self.dt * self.expV
        np.exp(self.expV, out=self.expV)

        # Pre-calculate the kinetic energy phase
        self.expK = self.K(self.P - 0.5*self.Lambda) - self.K(self.P + 0.5*self.Lambda)
        self.expK = 1j*self.dt * self.expK
        np.exp(self.expK, out=self.expK)

        """
        try:
            # Pre-calculate the coupling energy between ground and excited states, if time independent
            self._Veg_x_plus = self.Veg(self.x_plus)
            self._Veg_x_minus = self.Veg(self.x_minus)
        except TypeError:
            # If exception is generated, then the coupling is time-dependent
            # and caching is not possible
            pass

    def get_Veg(self, x, t):
        try:
            return self._Veg_x_plus if x is self.x_plus else self._Veg_x_minus
        except AttributeError:
            return self.Veg(x, t)
        """

    def get_CML(self, q, t):
        """
        Calculate C, M, L forming the elements of T matrix
        :param q: a shifted coordinate grid
        :param t: time
        :return: tuple C, M, L
        """
        assert q is self.x_plus or q is self.x_minus, \
            "the shifted coordinate (q) must be either x_plus or x_minus"

        # get the difference of adiabatic potential curves
        Vg_minus_Ve = (self._Vg_plus_Ve_x_plus if q is self.x_plus else self._Vg_minus_Ve_x_minus)

        Veg = self.Veg(q, t)

        D = Veg**2 + 0.25*Vg_minus_Ve**2
        np.sqrt(D, out=D)

        S = np.sinc(D * self.dt / np.pi)
        S *= self.dt

        C = D * self.dt
        np.cos(C, out=C)

        M = S * Vg_minus_Ve
        M *= 0.5

        L = S * Veg

        return C, M, L

    def get_T_left(self, t):
        """
        Return the elements of T matrix acting from the left in x-theta representation
        :param t: time
        :return: tuple Tg, Tge, Te
        """
        C, M, L = self.get_CML(self.x_minus, t)
        return C-1j*M, -1j*L, C+1j*M

    def get_T_right(self, t):
        """
        Return the elements of T matrix acting from the right in x-theta representation
        :param t: time
        :return: tuple Tg, Tge, Te
        """
        C, M, L = self.get_CML(self.x_plus, t)
        return C+1j*M, 1j*L, C-1j*M

    def single_step_propagation(self):
        """
        Perform single step propagation. The final Wigner functions are not normalized.
        """
        ################ p x -> theta x ################
        self.wigner_g = fftpack.fft(self.wigner_g, axis=0, overwrite_x=True)
        self.wigner_ge = fftpack.fft(self.wigner_ge, axis=0, overwrite_x=True)
        self.wigner_e = fftpack.fft(self.wigner_e, axis=0, overwrite_x=True)

        ################ Act with T matrix from the left ################
        Tg, Tge, Te = self.get_T_left(self.t)

        # Save previous version of the Wigner function
        Wg, Wge, We = self.wigner_g, self.wigner_ge, self.wigner_e

        self.wigner_g = Tg * Wg + Tge * Wge.conj()
        self.wigner_ge = Tg * Wge + Tge * We
        self.wigner_e = Tge * Wge + Te * We

        ################ Act with T matrix from the right ################
        Tg, Tge, Te = self.get_T_right(self.t)

        # Save previous version of the Wigner function
        Wg, Wge, We = self.wigner_g, self.wigner_ge, self.wigner_e

        self.wigner_g = Tg * Wg + Tge * Wge
        self.wigner_ge = Tge * Wg + Te * Wge
        self.wigner_e = Tge * Wge.conj() + Te * We

        ################ Apply the phase factor ################
        self.wigner_g *= self.expV
        self.wigner_ge *= self.expV
        self.wigner_e *= self.expV

        ################ theta x -> p x ################
        self.wigner_g = fftpack.ifft(self.wigner_g, axis=0, overwrite_x=True)
        self.wigner_ge = fftpack.ifft(self.wigner_ge, axis=0, overwrite_x=True)
        self.wigner_e = fftpack.ifft(self.wigner_e, axis=0, overwrite_x=True)

        ################ p x  ->  p lambda ################
        self.wigner_g = fftpack.fft(self.wigner_g, axis=1, overwrite_x=True)
        self.wigner_ge = fftpack.fft(self.wigner_ge, axis=1, overwrite_x=True)
        self.wigner_e = fftpack.fft(self.wigner_e, axis=1, overwrite_x=True)

        ################ Apply the phase factor ################
        self.wigner_g *= self.expK
        self.wigner_ge *= self.expK
        self.wigner_e *= self.expK

        ################ p lambda  ->  p x ################
        self.wigner_g = fftpack.ifft(self.wigner_g, axis=1, overwrite_x=True)
        self.wigner_ge = fftpack.ifft(self.wigner_ge, axis=1, overwrite_x=True)
        self.wigner_e = fftpack.ifft(self.wigner_e, axis=1, overwrite_x=True)

        #self.normalize_wigner_matrix()

    def normalize_wigner_matrix(self):
        """
        Normalize the wigner matrix
        :return:
        """
        norm = (self.wigner_g.sum() + self.wigner_e.sum())*self.dX*self.dP

        self.wigner_g /= norm
        self.wigner_ge /= norm
        self.wigner_e /= norm

    def set_wigner_matrix(self, Wg=0, Wge=0, We=0):
        """
        Set the initial Wigner function
        :param new_wigner_func: 2D numoy array contaning the wigner function
        :return: self
        """
        """
        # perform the consistency checks
        assert new_wigner_func.shape == (self.P.size, self.X.size), \
            "The grid sizes does not match with the Wigner function"

        # make sure the Wigner function is stored as a complex array
        self.wignerfunction = new_wigner_func + 0j

        # normalize
        self.wignerfunction /= self.wignerfunction.sum() * self.dX*self.dP
        """

        self.wigner_g, self.wigner_ge, self.wigner_e = Wg, Wge, We

        if not isinstance(Wg, np.ndarray):
            self.wigner_g = np.zeros((self.P_gridDIM, self.X_gridDIM), dtype=np.complex)

        if not isinstance(Wge, np.ndarray):
            self.wigner_ge = np.zeros((self.P_gridDIM, self.X_gridDIM), dtype=np.complex)

        if not isinstance(We, np.ndarray):
            self.wigner_e = np.zeros((self.P_gridDIM, self.X_gridDIM), dtype=np.complex)

        self.normalize_wigner_matrix()

        return self


##############################################################################
#
#   Run some examples
#
##############################################################################

if __name__ == '__main__':

    # load tools for creating animation
    import sys

    if sys.platform == 'darwin':
        # only for MacOS
        import matplotlib
        matplotlib.use('TKAgg')

    import matplotlib.pyplot as plt
    from matplotlib.animation import FuncAnimation

    # Use the documentation string for the developed class
    print(Molecule2StateWignerMoyal.__doc__)

    class VisualizeDynamicsPhaseSpace:
        """
        Class to visualize the Wigner function function dynamics in phase space.
        """
        def __init__(self, fig):
            """
            Initialize all propagators and frame
            :param fig: matplotlib figure object
            """
            #  Initialize systems
            self.set_quantum_sys()

            #################################################################
            #
            # Initialize plotting facility
            #
            #################################################################

            self.fig = fig

            # import utility to visualize the wigner function
            from wigner_normalize import WignerNormalize

            # bundle plotting settings
            imshow_settings = dict(
                origin='lower',
                cmap='seismic',
                norm=WignerNormalize(vmin=-0.1, vmax=0.1),
                extent=[self.molecule.X.min(), self.molecule.X.max(), self.molecule.P.min(), self.molecule.P.max()]
            )

            # generate plots
            ax = fig.add_subplot(221)
            ax.set_title('$W_{g}(x,p)$')
            self.wigner_g_img = ax.imshow([[]], **imshow_settings)
            ax.set_ylabel('$p$ (a.u.)')

            ax = fig.add_subplot(222)
            ax.set_title('$\\Re W_{ge}(x,p)$')
            self.re_wigner_ge_img = ax.imshow([[]], **imshow_settings)
            ax.set_ylabel('$p$ (a.u.)')

            ax = fig.add_subplot(223)
            ax.set_title('$\\Im W_{eg}(x,p)$')
            self.im_wigner_ge_img = ax.imshow([[]], **imshow_settings)
            ax.set_xlabel('$x$ (a.u.)')
            ax.set_ylabel('$p$ (a.u.)')

            ax = fig.add_subplot(224)
            ax.set_title('$W_{e}(x,p)$')
            self.wigner_e_img = ax.imshow([[]], **imshow_settings)
            ax.set_xlabel('$x$ (a.u.)')
            ax.set_ylabel('$p$ (a.u.)')

            # self.fig.colorbar(self.img)

        def set_quantum_sys(self):
            """
            Initialize quantum propagator
            :param self:
            :return:
            """
            self.molecule = Molecule2StateWignerMoyal(
                t=0.,
                dt=0.005,
                X_gridDIM=256,
                X_amplitude=10.,
                P_gridDIM=256,
                P_amplitude=10.,
                # kinetic energy part of the hamiltonian
                K=lambda p: 0.5*p**2,
                # potential energy part of the hamiltonian
                Vg=lambda x: 0.5*2.9*x**2, #+ 0.00001*x**4,
                Ve=lambda x: 0.5*1*x**2,
                Veg=lambda x,t: 0.1*x
            )

            self.molecule.set_wigner_matrix(
                Wg=np.exp(-(self.molecule.P + 2.)**2 -self.molecule.X**2)
            )

        def empty_frame(self):
            """
            Make empty frame and reinitialize quantum system
            :param self:
            :return: image object
            """
            self.set_quantum_sys()

            self.wigner_g_img.set_array([[]])
            self.re_wigner_ge_img.set_array([[]])
            self.im_wigner_ge_img.set_array([[]])
            self.wigner_e_img.set_array([[]])

            return self.wigner_g_img, self.re_wigner_ge_img, self.im_wigner_ge_img, self.wigner_e_img

        def __call__(self, frame_num):
            """
            Draw a new frame
            :param frame_num: current frame number
            :return: image objects
            """
            for _ in xrange(10):
                self.molecule.single_step_propagation()

            self.wigner_g_img.set_array(self.molecule.wigner_g.real)
            self.re_wigner_ge_img.set_array(self.molecule.wigner_ge.real)
            self.im_wigner_ge_img.set_array(self.molecule.wigner_ge.imag)
            self.wigner_e_img.set_array(self.molecule.wigner_e.real)

            return self.wigner_g_img, self.re_wigner_ge_img, self.im_wigner_ge_img, self.wigner_e_img


    fig = plt.gcf()
    visualizer = VisualizeDynamicsPhaseSpace(fig)
    animation = FuncAnimation(fig, visualizer, frames=np.arange(100),
                              init_func=visualizer.empty_frame, repeat=True, blit=True)
    plt.show()

