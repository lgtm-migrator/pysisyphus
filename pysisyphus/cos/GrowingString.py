import numpy as np
from scipy.interpolate import splprep, splev

from pysisyphus.constants import AU2KJPERMOL
from pysisyphus.cos.ChainOfStates import ChainOfStates
from pysisyphus.cos.GrowingChainOfStates import GrowingChainOfStates

# [1] https://aip.scitation.org/doi/abs/10.1063/1.1691018
#     Peters, 2004
# [2] https://aip.scitation.org/doi/abs/10.1063/1.4804162
#     Zimmerman, 2013


class GrowingString(GrowingChainOfStates):

    def __init__(self, images, calc_getter, perp_thresh=0.05,
                 reparam_every=2, reparam_every_full=3, reparam_tol=None,
                 reparam_check="norm", max_micro_cycles=5, **kwargs):
        assert len(images) >= 2, "Need at least 2 images for GrowingString."
        if len(images) > 2:
            images = [images[0], images[-1]]
            print("More than 2 images given. Will only use first and last image!")

        super().__init__(images, calc_getter, **kwargs)

        self.perp_thresh = perp_thresh
        self.reparam_every = int(reparam_every)
        self.reparam_every_full = int(reparam_every_full)
        assert self.reparam_every >= 1 and self.reparam_every_full >= 1, \
            "reparam_every and reparam_every_full must be positive integers!"
        if reparam_tol is not None:
            self.reparam_tol = float(reparam_tol)
            assert self.reparam_tol > 0
        else:
            self.reparam_tol = 1 / (self.max_nodes + 2) / 2
        self.log(f"Using reparametrization tolerance of {self.reparam_tol:.4f}")
        self.reparam_check = reparam_check
        assert self.reparam_check in ("norm", "rms")
        self.max_micro_cycles= int(max_micro_cycles)

        left_img, right_img = self.images

        self.left_string = [left_img, ]
        self.right_string = [right_img, ]

        # The desired spacing of the nodes in the final string on the
        # normalized arclength.
        self.sk = 1 / (self.max_nodes+1)

        self.reparam_in = reparam_every
        self._tangents = None
        self.tangent_list = list()
        self.perp_forces_list = list()
        self.coords_list = list()

        left_frontier = self.get_new_image(self.lf_ind)
        self.left_string.append(left_frontier)
        right_frontier = self.get_new_image(self.rf_ind)
        self.right_string.append(right_frontier)

        if self.coord_type == "cart":
            self.set_tangents()

    def get_cur_param_density(self, kind="cart"):
        if kind == "cart":
            coords = np.array([image.cart_coords for image in self.images])
            coords_ = coords.reshape(len(self.images), -1)
            diffs = coords_ - coords_[0]
        elif kind == "coords":
            image0 = self.images[0]
            # This way, even with DLC all differences will be given in the
            # active set of image0.
            diffs = np.array([image0-image for image in self.images])
        else:
            raise Exception("Invalid kind")

        norms = np.linalg.norm(diffs, axis=1)
        cur_param_density = norms / norms.max()
        # Assert that the last (rightmost) image is also the one that is the
        # farthest away from the first (leftmost) image.
        assert norms[-1] == norms.max(), \
            "Unexpected parametrization density. Expected the last " \
            "(rightmost) image to be the farthest image, but this is " \
            "not the case. Current parametrization density is: " \
           f"{cur_param_density}."
        return cur_param_density

    def get_new_image(self, ref_index):
        """Get new image by taking a step from self.images[ref_index] towards
        the center of the string."""
        new_img = self.images[ref_index].copy(check_bends=False)

        if ref_index <= self.lf_ind:
            tangent_ind = ref_index + 1
            insert_ind = tangent_ind
        else:
            tangent_ind = ref_index - 1
            insert_ind = ref_index
        tangent_img = self.images[tangent_ind]

        # (new_img - tangent_img) points from tangent_img towards new_img.
        # As we want to derive a new image from new_img, we have to step
        # against this vector, so we have to multiply by -1.
        # Why don't we just use (tangent_img - new_img) to get the right
        # direction? In DLC the resulting distance would then be given in
        # the active set U of tangent_img, but we need it in the active set U
        # of new_img.
        # Formulated the other way around the same expression can be used for
        # all coord types.
        distance = -(new_img - tangent_img)

        # The desired step(_length) for the new image be can be easily determined
        # from a simple rule of proportion by relating the actual distance between
        # two images to their parametrization density difference on the normalized
        # arclength and the desired spacing given by self.sk.
        #
        # Δparam_density / distance = self.sk / step
        # step = self.sk / Δparam_density * distance
        cpd = self.get_cur_param_density("coords")
        # As we always want to step in the direction of 'distance' we just take
        # the absolute value of the difference, as we are not interested in the
        # sign.
        param_dens_diff = abs(cpd[ref_index] - cpd[tangent_ind])
        step_length = self.sk / param_dens_diff
        step = step_length * distance

        new_coords = new_img.coords + step
        new_img.coords = new_coords
        new_img.set_calculator(self.calc_getter())
        ref_calc = self.images[ref_index].calculator
        try:
            chkfiles = ref_calc.get_chkfiles()
            new_img.calculator.set_chkfiles(chkfiles)
            self.log( "Set checkfiles from calculator of node "
                     f"{ref_index:02d} on calculator of new node."
            )
        except AttributeError:
            self.log("Calculator doesn't support 'get/set_chkfiles()'")
        self.images.insert(insert_ind, new_img)
        self.log(f"Created new image; inserted it before index {insert_ind}.")
        return new_img

        # self.images.insert(insert_ind, new_img)
        # # Take smaller steps, as the internal-cartesian-backconversion may be
        # # unstable for bigger steps.
        # steps = 10
        # step = step_length * distance/steps
        # for i in range(steps):
            # new_coords = new_img.coords + step
            # new_img.coords = new_coords
            # cpd = self.get_cur_param_density("coords")
            # try:
                # if new_img.internal.backtransform_failed:
                    # import pdb; pdb.set_trace()
            # except AttributeError:
                # pass
            # print(f"{i:02d}: {cpd}")

        # # self.images.insert(insert_ind, new_img)
        # # self.log(f"Created new image; inserted it before index {insert_ind}.")

        # cpd = self.get_cur_param_density("coords")
        # self.log(f"Current param_density: {cpd}")

        # return new_img

    @property
    def left_size(self):
        return len(self.left_string)

    @property
    def right_size(self):
        return len(self.right_string)

    @property
    def string_size(self):
        return self.left_size + self.right_size

    @property
    def fully_grown(self):
        """Returns wether the string is fully grown. Don't count the first
        and last node."""
        return not ((self.string_size - 2) < self.max_nodes)

    @property
    def nodes_missing(self):
        """Returns the number of nodes to be grown."""
        return (self.max_nodes + 2) - self.string_size

    @property
    def lf_ind(self):
        """Index of the left frontier node in self.images."""
        return len(self.left_string)-1

    @property
    def rf_ind(self):
        """Index of the right frontier node in self.images."""
        return self.lf_ind+1

    @property
    def full_string_image_inds(self):
        left_inds = np.arange(self.left_size)
        right_inds = np.arange(self.max_nodes+2)[-self.right_size:]
        image_inds = np.concatenate((left_inds, right_inds))
        return image_inds

    @property
    def image_inds(self):
        return self.full_string_image_inds

    def spline(self):
        reshaped = self.coords.reshape(-1, self.coords_length)
        # To use splprep we have to transpose the coords.
        transp_coords = reshaped.transpose()
        # Spline in batches as scipy can't handle > 11 rows at once
        tcks, us = zip(*[splprep(transp_coords[i:i+9], s=0, k=3)
                         for i in range(0, len(transp_coords), 9)]
        )
        return tcks, us

    def reparam_cart(self, desired_param_density):
        tcks, us = self.spline()
        # Reparametrize mesh
        new_points = np.vstack([splev(desired_param_density, tck) for tck in tcks])
        # Flatten along first dimension.
        new_points = new_points.reshape(-1, len(self.images))
        self.coords = new_points.transpose().flatten()

    def reparam_dlc(self, cur_param_density, desired_param_density, thresh=1e-3):
        # Reparametrization will take place along the tangent between two
        # images. The index of the tangent image depends on wether the image
        # is above or below the desired param_density on the normalized arc.

        # This implementation assumes that the reparametrization step take is not
        # too big, so the internal-cartesian-transformation doesn't fail.
        # Adding new images is done with smaller steps to avoid this problem.
        # As every images is added only once, but may be reparametrized quite often
        # we try to do the reparametrization in one step.
        # A safer approach would be to do it in multiple smaller steps.

        self.log(f"Density before reparametrization: {cur_param_density}")
        for i, reparam_image in enumerate(self.images[1:-1], 1):
            self.log(f"Reparametrizing node {i}")
            for j in range(self.max_micro_cycles):
                diff = (desired_param_density - cur_param_density)[i]
                self.log(f"\t{j}: Δ={diff:.6f}")
                if abs(diff) < self.reparam_tol:
                    break
                # Negative sign: image is too far right and has to be shifted left.
                # Positive sign: image is too far left and has to be shifted right.
                sign = int(np.sign(diff))
                if abs(diff) < thresh:
                    continue
                # Index of the tangent image. reparam_image will be shifted along
                # this direction to achieve the desired parametirzation density.
                tangent_ind = i + sign
                tangent_image = self.images[tangent_ind]
                distance = -(reparam_image - tangent_image)

                param_dens_diff = abs(cur_param_density[tangent_ind] - cur_param_density[i])
                step_length = abs(diff) / param_dens_diff
                step = step_length * distance
                reparam_coords = reparam_image.coords + step
                reparam_image.coords = reparam_coords
                cur_param_density = self.get_cur_param_density("coords")
            else:
                self.log(f"Reparametrization of node {i} did not converge after "
                         f"{self.max_micro_cycles}. Breaking!")
                break

        cpd_str = np.array2string(cur_param_density, precision=4)
        self.log(f"Param density after reparametrization: {cpd_str}")

        try:
            np.testing.assert_allclose(cur_param_density, desired_param_density,
                                       atol=self.reparam_tol)
        except AssertionError as err:
            trj_str = self.as_xyz()
            fn = "failed_reparametrization.trj"
            with open(fn, "w") as handle:
                handle.write(trj_str)
            print("Wrote coordinates of failed reparametrization to '{fn}'")
            raise err

        # Regenerate active set after reparametrization
        # [image.internal.set_active_set() for image in self.moving_images]

    def set_tangents(self):
        """Set tangents as given by the first derivative of a cubic spline.

        Tangent-calculation by splining requires the information of all
        images at once. To avoid the repeated splining of all images whenever
        a tangent is requested this method calculates all tangents and stores
        them in the self._tangents, that can be accessed via the self.tangents
        property.

        !!! Right now one must not forget to call this method
        after coordinate modification, e.g. after
        reparametrization!  Otherwise wrong (old) tangets are used. !!!
        """

        tcks, us = self.spline()
        Sk, cur_mesh = self.arc_dims
        self.log(f"Total arclength Sk={Sk:.4f}")
        tangents = np.vstack([splev(cur_mesh, tck, der=1) for tck in tcks]).T
        norms = np.linalg.norm(tangents, axis=1)
        tangents = tangents / norms[:,None]
        # Tangents of the right string shall point towards the center, so
        # we reverse their orientation.
        tangents[self.rf_ind:] *= -1
        self._tangents = tangents

    def get_tangent(self, i):
        # Use splined tangents with cartesian coordinates that were set in a
        # self.set_tangents() call.
        if self.coord_type == "cart":
            return self._tangents[i]

        # With DLC we can use conventional tangents that can be calculated
        # without splining.

        # Upwinding tangent when the string is fully grown.
        if self.fully_grown:
            return super().get_tangent(i, kind="upwinding")

        # During the growth phase we use simple tangents that always point
        # towards the center of the string.
        cur_image = self.images[i]
        if i <= self.lf_ind:
            next_ind = i + 1
        else:
            next_ind = i - 1
        next_image = self.images[next_ind]
        tangent = next_image - cur_image
        tangent /= np.linalg.norm(tangent)
        return tangent

    @ChainOfStates.forces.getter
    def forces(self):
        if self._forces is None:
            self.calculate_forces()

        indices = range(len(self.images))
        # In constrast to NEB calculations we only use the perpendicular component
        # of the force, without any spring forces. A desired image distribution is
        # achieved via periodic reparametrization.
        perp_forces = np.array([self.get_perpendicular_forces(i) for i in indices])
        self.perp_forces_list.append(perp_forces.copy().flatten())
        # Add climbing forces
        total_forces = self.set_climbing_forces(perp_forces)
        self._forces = total_forces.flatten()
        return self._forces

    def reparametrize(self):
        reparametrized = False
        # If this counter reaches 0 reparametrization will occur.
        self.reparam_in -= 1

        # Check if new images can be added for incomplete strings.
        if not self.fully_grown:
            perp_forces  = self.perp_forces_list[-1].reshape(len(self.images), -1)
            # Calculate norm and rms of the perpendicular force for every
            # node/image on the string.
            to_check = {
                "norm": np.linalg.norm(perp_forces, axis=1),
                "rms": np.sqrt(np.mean(perp_forces**2, axis=1)),
            }
            self.log(f"Checking frontier node convergence, threshold={self.perp_thresh:.6f}")
            # We can add a new node if the norm/rms of the perpendicular force is below
            # the threshold.
            def converged(i):
                cur_val = to_check[self.reparam_check][i]
                is_converged = cur_val <= self.perp_thresh
                conv_str = ", converged" if is_converged else ""
                self.log(f"\tnode {i:02d}: {self.reparam_check}(perp_forces)={cur_val:.6f}"
                         f"{conv_str}")
                return is_converged

            # New images are added with the same coordinates as the frontier image.
            # We force reparametrization by setting self.reparam_in to 0 to get sane
            # coordinates for the new image(s).
            if converged(self.lf_ind):
                # Insert at the end of the left string, just before the
                # right frontier node.
                new_left_frontier = self.get_new_image(self.lf_ind)
                self.left_string.append(new_left_frontier)
                self.log("Added new left frontier node.")
                self.reparam_in = 0
            # If an image was just grown in the left substring the string may now
            # be fully grown, so we reavluate 'self.fully_grown' here.
            if (not self.fully_grown) and converged(self.rf_ind):
                # Insert at the end of the right string, just before the
                # current right frontier node.
                new_right_frontier = self.get_new_image(self.rf_ind)
                self.right_string.append(new_right_frontier)
                self.log("Added new right frontier node.")
                self.reparam_in = 0

        self.log(
            f"Current string size is {self.left_size}+{self.right_size}="
            f"{self.string_size}. There are still {self.nodes_missing} "
            "nodes to be grown."
            if not self.fully_grown else "String is fully grown."
        )

        if self.reparam_in > 0:
            self.log("Skipping reparametrization. Next reparametrization in "
                     f"{self.reparam_in} cycles.")
        else:
            # Prepare image reparametrization
            desired_param_density = self.sk*self.full_string_image_inds
            pd_str = np.array2string(desired_param_density, precision=4)
            self.log(f"Desired param density: {pd_str}")

            # Reparametrize images.
            if self.coord_type == "cart":
                self.reparam_cart(desired_param_density)
                self.set_tangents()
            elif self.coord_type == "dlc":
                cur_param_density = self.get_cur_param_density("coords")
                self.reparam_dlc(cur_param_density, desired_param_density)
            else:
                raise Exception("How did you get here?")

            self.reparam_in = self.reparam_every_full if self.fully_grown \
                              else self.reparam_every
            reparametrized = True

        if self.coord_type == "cart":
            self.set_tangents()
        return reparametrized

    def get_additional_print(self):
        size_str = f"{self.left_size}+{self.right_size}"
        if self.fully_grown:
            size_str = "Full"
        size_info = f"String={size_str}"
        energies = np.array(self.all_energies[-1])
        barrier = (energies.max() - energies[0]) * AU2KJPERMOL
        barrier_info = f"(E_max-E_0)={barrier:.1f} kJ/mol"
        hei_ind = energies.argmax()
        hei_str = f"HEI={hei_ind+1:02d}/{energies.size:02d}"

        tot = f"Grads={self.get_image_calc_counter_sum()}"

        strs = (
            size_info,
            hei_str,
            barrier_info,
        )
        return "\t" + " ".join(strs)
